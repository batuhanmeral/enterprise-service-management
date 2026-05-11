from django.shortcuts import get_object_or_404
from django.db.models import Q

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from departments.models import Department, Category
from identity.models import Role, User
from notifications.models import Notification

from .filters import TicketFilter
from .models import Ticket, TicketComment, Status as TicketStatus, TicketActionType
from .serializers import (
    TicketListSerializer, TicketDetailSerializer,
    TicketCreateSerializer, TicketUpdateSerializer,
    TicketResolveSerializer, TicketRejectResolutionSerializer,
    TicketCsatSerializer, TicketTransferSerializer,
    TicketCommentSerializer,
)


# Audit log yardımcı fonksiyonu — SSR view'larıyla aynı (TicketHistory + AuditLog)
from .views import log_ticket_action  # noqa: E402


# Bilet Listeleme ve Oluşturma


class TicketListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    # django-filter: ?status=OPEN&priority=HIGH&department=2&created_at_after=2026-01-01
    filterset_class = TicketFilter
    # OrderingFilter: ?ordering=-created_at  (varsayılan -created_at)
    ordering_fields = ['created_at', 'status', 'priority', 'subject']
    ordering = ['-created_at']
    # SearchFilter: ?search=fatura
    search_fields = ['subject', 'message']

    # POST için scope-throttle (saatte 30 bilet/kullanıcı) — spam koruması
    def get_throttles(self):
        if self.request.method == 'POST':
            return [ScopedRateThrottle()]
        return super().get_throttles()
    throttle_scope = 'ticket_create'

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TicketCreateSerializer
        return TicketListSerializer

    def get_queryset(self):
        # Schema üretimi için (drf-spectacular) erken çıkış
        if getattr(self, 'swagger_fake_view', False):
            return Ticket.objects.none()

        user = self.request.user
        qs = Ticket.objects.select_related(
            'sender', 'assigned_to', 'department', 'category',
        )

        # Rol bazlı erişim kısıtlaması (filtre değil — yetkilendirme)
        # AGENT/MANAGER: departman biletleri + kendi açtıkları (departmansız ise yalnızca kendi).
        if user.role == Role.ADMIN:
            return qs
        if user.role in (Role.AGENT, Role.MANAGER):
            if user.department_id:
                return qs.filter(Q(department=user.department) | Q(sender=user))
            return qs.filter(sender=user)
        return qs.filter(sender=user)

    def perform_create(self, serializer):
        user = self.request.user
        # Mikroservis (ADMIN) ise payload'da gelen sender'ı kullan, değilse request.user
        sender = serializer.validated_data.pop('sender', None) if user.role == Role.ADMIN else None
        sender = sender or user
        ticket = serializer.save(sender=sender, status=TicketStatus.OPEN)
        log_ticket_action(ticket, user, 'Bilet oluşturuldu.',
                          action_type=TicketActionType.CREATED)
        from .views import _notify_department_on_new_ticket
        _notify_department_on_new_ticket(ticket, exclude_user=user)


# Bilet Detay, Güncelleme ve Silme


class TicketDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return TicketDetailSerializer
        return TicketUpdateSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Ticket.objects.none()

        user = self.request.user
        qs = Ticket.objects.select_related(
            'sender', 'assigned_to', 'department', 'category',
        ).prefetch_related('history__actor')

        if user.role == Role.ADMIN:
            return qs
        elif user.role in (Role.AGENT, Role.MANAGER):
            return qs.filter(
                Q(department=user.department) | Q(sender=user)
            )
        else:
            return qs.filter(sender=user)

    def perform_update(self, serializer):
        user = self.request.user
        ticket = self.get_object()

        # Güncelleme yetkisi: sender (OPEN) veya Admin (Mikroservis)
        if user.role != Role.ADMIN:
            if ticket.sender != user or ticket.status != TicketStatus.OPEN:
                raise PermissionDenied('Sadece açık durumdaki kendi biletlerinizi güncelleyebilirsiniz.')
            # Normal kullanıcı status veya assigned_to değiştiremez
            serializer.validated_data.pop('status', None)
            serializer.validated_data.pop('assigned_to', None)

        serializer.save()
        log_ticket_action(ticket, user, 'Bilet güncellendi.',
                          action_type=TicketActionType.UPDATED)

    def perform_destroy(self, instance):
        user = self.request.user

        is_sender_open = (instance.sender == user and instance.status == TicketStatus.OPEN)
        is_admin = (user.role == Role.ADMIN)
        is_dept_manager = (
            user.role == Role.MANAGER
            and instance.department == user.department
        )

        if not (is_sender_open or is_admin or is_dept_manager):
            raise PermissionDenied(
                'Sadece talep sahibi (açık biletler), ilgili yönetici veya Admin silebilir.'
            )

        instance.delete()


# Bilet Üstlenme (OPEN → IN_PROGRESS)


@extend_schema(
    tags=['tickets'],
    request=None,
    responses={200: TicketDetailSerializer, 400: OpenApiResponse(), 403: OpenApiResponse()},
)
class TicketTakeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user

        if user.role not in (Role.AGENT, Role.MANAGER):
            return Response(
                {'detail': 'Bu işlem için yetkiniz bulunmamaktadır.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        ticket = get_object_or_404(Ticket, pk=pk)

        if ticket.department != user.department:
            return Response(
                {'detail': 'Bu bilet sizin departmanınıza ait değildir.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if ticket.status != TicketStatus.OPEN:
            return Response(
                {'detail': 'Bu bilet zaten işlemde veya kapalı durumda.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket.take_into_process(personnel=user)
        log_ticket_action(ticket, user, f'{user.get_full_name() or user.username} bileti üstlendi.',
                          action_type=TicketActionType.TAKEN)

        # Talep sahibine bildirim
        if ticket.sender:
            Notification.objects.create(
                recipient=ticket.sender,
                ticket=ticket,
                message=(
                    f'Talebiniz "{ticket.subject}" (#{ticket.pk}) '
                    f'{user.get_full_name() or user.username} tarafından '
                    f'işleme alınmıştır.'
                ),
            )

        return Response(TicketDetailSerializer(ticket).data)


# Bileti çözüldü olarak işaretleme (IN_PROGRESS → RESOLVED, talep sahibinin onayı bekleniyor)


@extend_schema(
    tags=['tickets'],
    request=TicketResolveSerializer,
    responses={200: TicketDetailSerializer, 400: OpenApiResponse(), 403: OpenApiResponse()},
)
class TicketResolveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        ticket = get_object_or_404(Ticket, pk=pk)

        is_assigned = (ticket.assigned_to == user)
        is_admin = (user.role == Role.ADMIN)

        if not (is_assigned or is_admin):
            return Response(
                {'detail': 'Sadece bileti üstlenen personel veya Admin çözüm işaretleyebilir.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if ticket.status != TicketStatus.IN_PROGRESS:
            return Response(
                {'detail': 'Sadece "İşlemde" durumundaki biletler çözüldü olarak işaretlenebilir.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TicketResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        resolution_note = serializer.validated_data['resolution_note']
        ticket.mark_resolved(resolution_note=resolution_note)
        log_ticket_action(
            ticket, user, f'Bilet çözüldü olarak işaretlendi. Çözüm: {resolution_note[:100]}',
            action_type=TicketActionType.RESOLVED,
        )

        if ticket.sender:
            Notification.objects.create(
                recipient=ticket.sender,
                ticket=ticket,
                message=(
                    f'Talebiniz "{ticket.subject}" (#{ticket.pk}) çözüldü olarak işaretlendi. '
                    f'Lütfen onaylayın (3 gün içinde otomatik kapanır).'
                ),
            )

        return Response(TicketDetailSerializer(ticket).data)


# Çözüm onayı (RESOLVED → CLOSED, sender)


@extend_schema(
    tags=['tickets'],
    request=None,
    responses={200: TicketDetailSerializer, 400: OpenApiResponse(), 403: OpenApiResponse()},
)
class TicketConfirmResolutionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        ticket = get_object_or_404(Ticket, pk=pk)

        if ticket.sender != user:
            return Response({'detail': 'Sadece talep sahibi onay verebilir.'},
                            status=status.HTTP_403_FORBIDDEN)
        if ticket.status != TicketStatus.RESOLVED:
            return Response({'detail': 'Sadece "Çözüldü" biletler için geçerli.'},
                            status=status.HTTP_400_BAD_REQUEST)

        ticket.confirm_resolution()
        log_ticket_action(
            ticket, user, 'Talep sahibi sorununun çözüldüğünü onayladı; bilet kapatıldı.',
            action_type=TicketActionType.RESOLUTION_CONFIRMED,
        )
        return Response(TicketDetailSerializer(ticket).data)


# Çözüm reddi (RESOLVED → IN_PROGRESS / ESCALATED, sender, gerekçe zorunlu)


@extend_schema(
    tags=['tickets'],
    request=TicketRejectResolutionSerializer,
    responses={200: TicketDetailSerializer, 400: OpenApiResponse(), 403: OpenApiResponse()},
)
class TicketRejectResolutionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        ticket = get_object_or_404(Ticket, pk=pk)

        if ticket.sender != user:
            return Response({'detail': 'Sadece talep sahibi red verebilir.'},
                            status=status.HTTP_403_FORBIDDEN)
        if ticket.status != TicketStatus.RESOLVED:
            return Response({'detail': 'Sadece "Çözüldü" biletler reddedilebilir.'},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = TicketRejectResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['reason']

        reopened = ticket.reject_resolution(reason)
        if reopened:
            log_ticket_action(
                ticket, user,
                f'Talep sahibi çözümü reddetti (#{ticket.reopen_count}/2). Gerekçe: {reason[:120]}',
                action_type=TicketActionType.RESOLUTION_REJECTED,
            )
        else:
            log_ticket_action(
                ticket, user,
                f'Çözüm 3. kez reddedildi; bilet eskalasyona alındı. Gerekçe: {reason[:120]}',
                action_type=TicketActionType.ESCALATED,
            )
        return Response(TicketDetailSerializer(ticket).data)


# CSAT puanlama (CLOSED, sender, 1-5)


@extend_schema(
    tags=['tickets'],
    request=TicketCsatSerializer,
    responses={200: TicketDetailSerializer, 400: OpenApiResponse(), 403: OpenApiResponse()},
)
class TicketCsatAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        ticket = get_object_or_404(Ticket, pk=pk)

        if ticket.sender != user:
            return Response({'detail': 'Sadece talep sahibi puan verebilir.'},
                            status=status.HTTP_403_FORBIDDEN)
        if ticket.status != TicketStatus.CLOSED:
            return Response({'detail': 'Sadece kapanmış biletler puanlanabilir.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if ticket.csat_rating is not None:
            return Response({'detail': 'Bu bilet için zaten puan verilmiş.'},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = TicketCsatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket.set_csat(serializer.validated_data['rating'])
        log_ticket_action(
            ticket, user, f'Memnuniyet puanı verildi: {ticket.csat_rating}/5',
            action_type=TicketActionType.CSAT_RATED,
        )
        return Response(TicketDetailSerializer(ticket).data)


# Bilet Transfer (Departmanlar arası aktarım)


@extend_schema(
    tags=['tickets'],
    request=TicketTransferSerializer,
    responses={200: TicketDetailSerializer, 400: OpenApiResponse(), 403: OpenApiResponse()},
)
class TicketTransferAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        ticket = get_object_or_404(Ticket, pk=pk)

        if user.role not in (Role.AGENT, Role.MANAGER, Role.ADMIN):
            return Response(
                {'detail': 'Bu işlem için yetkiniz bulunmamaktadır.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Agent/Manager sadece kendi departman biletlerini transfer edebilir
        if user.role in (Role.AGENT, Role.MANAGER):
            if ticket.department != user.department:
                return Response(
                    {'detail': 'Bu bilet sizin departmanınıza ait değildir.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        if ticket.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.ESCALATED):
            return Response(
                {'detail': 'Bu durumdaki biletler transfer edilemez.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TicketTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_dept_id = serializer.validated_data['department']
        new_cat_id = serializer.validated_data.get('category')

        new_department = get_object_or_404(Department, pk=new_dept_id)
        new_category = None
        if new_cat_id:
            new_category = get_object_or_404(Category, pk=new_cat_id, department=new_department)

        old_department = ticket.department
        old_assigned = ticket.assigned_to

        ticket.transfer(new_department, new_category)
        log_ticket_action(
            ticket, user,
            f'Bilet {old_department.name if old_department else "?"} → {new_department.name} departmanına transfer edildi.',
            action_type=TicketActionType.TRANSFERRED,
        )

        # Talep sahibine bildirim
        if ticket.sender:
            Notification.objects.create(
                recipient=ticket.sender,
                ticket=ticket,
                message=(
                    f'Talebiniz "{ticket.subject}" (#{ticket.pk}) '
                    f'{new_department.name} departmanına transfer edilmiştir.'
                ),
            )

        # Eski atanan personele bildirim
        if old_assigned and old_assigned != user:
            Notification.objects.create(
                recipient=old_assigned,
                ticket=ticket,
                message=(
                    f'Üstlendiğiniz bilet "{ticket.subject}" (#{ticket.pk}) '
                    f'{new_department.name} departmanına transfer edildi.'
                ),
            )

        # Yeni departman ekibine giriş + eski departman ekibine çıkış bildirimi
        from .views import _notify_department_on_new_ticket, _notify_department_on_ticket_left
        _notify_department_on_new_ticket(ticket, exclude_user=user)
        _notify_department_on_ticket_left(ticket, old_department, exclude_user=user)

        return Response(TicketDetailSerializer(ticket).data)


# Bilet Yorum Listeleme ve Ekleme


class TicketCommentListCreateAPIView(ListCreateAPIView):
    serializer_class = TicketCommentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return TicketComment.objects.none()
        return TicketComment.objects.filter(ticket_id=self.kwargs['pk']).select_related('author')

    def perform_create(self, serializer):
        user = self.request.user
        ticket = get_object_or_404(Ticket, pk=self.kwargs['pk'])

        # Erişim kontrolü: sender, aynı departman personeli/yöneticisi veya admin
        if user.role == Role.ADMIN:
            pass
        elif user.role in (Role.AGENT, Role.MANAGER):
            if ticket.department != user.department and ticket.sender != user:
                raise PermissionDenied('Bu bilete yorum yapamazsınız.')
        elif ticket.sender != user:
            raise PermissionDenied('Bu bilete yorum yapamazsınız.')

        serializer.save(ticket=ticket, author=user)

        # Talep sahibi yorum yazdıysa personele bildir; personel yazdıysa talep sahibine bildir
        recipient = ticket.assigned_to if user == ticket.sender else ticket.sender
        if recipient:
            Notification.objects.create(
                recipient=recipient,
                ticket=ticket,
                message=(
                    f'"{ticket.subject}" (#{ticket.pk}) biletine '
                    f'{user.get_full_name() or user.username} yorum ekledi.'
                ),
            )


# Bilet Yeniden Açma (CLOSED → OPEN)


@extend_schema(
    tags=['tickets'],
    request=None,
    responses={200: TicketDetailSerializer, 400: OpenApiResponse(), 403: OpenApiResponse()},
)
class TicketReopenAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        ticket = get_object_or_404(Ticket, pk=pk)

        if user.role != Role.ADMIN:
            return Response(
                {'detail': 'Sadece Admin kilitlenmiş bir bileti yeniden açabilir.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if ticket.status not in (TicketStatus.CLOSED, TicketStatus.ESCALATED):
            return Response(
                {'detail': 'Sadece kilitli (Kapalı veya Eskalasyon) biletler yeniden açılabilir.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket.reopen()
        log_ticket_action(ticket, user, 'Bilet yeniden açıldı.',
                          action_type=TicketActionType.REOPENED)

        # Departman personeline bildirim
        if ticket.department:
            agents = User.objects.filter(
                department=ticket.department,
                role__in=[Role.AGENT, Role.MANAGER],
                is_active=True,
            ).exclude(pk=user.pk)
            notifications = [
                Notification(
                    recipient=agent,
                    ticket=ticket,
                    message=f'"{ticket.subject}" (#{ticket.pk}) bileti yeniden açıldı.',
                )
                for agent in agents
            ]
            if notifications:
                Notification.objects.bulk_create(notifications)

        return Response(TicketDetailSerializer(ticket).data)
