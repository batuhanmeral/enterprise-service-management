from datetime import date as _date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView, TemplateView
from identity.views import AdminRequiredMixin
from django.urls import reverse_lazy
from django.http import HttpResponseForbidden, JsonResponse
from django.contrib import messages
from django.db.models import Q, Case, When, IntegerField, F

from .models import Ticket, Status, Priority, TicketHistory, TicketActionType, TicketComment, TicketAttachment, Tag
from notifications.models import Notification
from identity.models import Role, User as UserModel
from identity.audit import audit_log, AuditCategory


# Geçmiş (sistem genelinde tüm aksiyonlar — AuditLog) — Sadece ADMIN.
class AuditLogListView(LoginRequiredMixin, ListView):
    template_name = 'tickets/audit_log.html'
    context_object_name = 'entries'
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != Role.ADMIN:
            return HttpResponseForbidden('Bu sayfaya erişim yetkiniz bulunmamaktadır.')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        from identity.models import AuditLog
        qs = (
            AuditLog.objects
            .select_related('actor', 'ticket', 'department')
            .order_by('-created_at')
        )

        actor_id = self.request.GET.get('actor')
        if actor_id and actor_id.isdigit():
            qs = qs.filter(actor_id=int(actor_id))

        category = self.request.GET.get('category')
        if category and category in dict(AuditLog.Category.choices):
            qs = qs.filter(category=category)

        department_id = self.request.GET.get('department')
        if department_id and department_id.isdigit():
            qs = qs.filter(department_id=int(department_id))

        date_from = self.request.GET.get('date_from')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = self.request.GET.get('date_to')
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(action__icontains=q)

        return qs

    def get_context_data(self, **kwargs):
        from identity.models import AuditLog
        from departments.models import Department
        context = super().get_context_data(**kwargs)
        context['actors'] = (
            UserModel.objects
            .filter(audit_actions__isnull=False)
            .distinct()
            .order_by('first_name', 'last_name', 'username')
        )
        context['departments'] = Department.objects.order_by('name')
        context['categories'] = AuditLog.Category.choices
        context['current_actor'] = self.request.GET.get('actor', '')
        context['current_category'] = self.request.GET.get('category', '')
        context['current_department'] = self.request.GET.get('department', '')
        context['current_date_from'] = self.request.GET.get('date_from', '')
        context['current_date_to'] = self.request.GET.get('date_to', '')
        context['current_q'] = self.request.GET.get('q', '')
        return context


PRIORITY_ORDER = Case(
    When(priority=Priority.URGENT, then=4),
    When(priority=Priority.HIGH, then=3),
    When(priority=Priority.NORMAL, then=2),
    When(priority=Priority.LOW, then=1),
    output_field=IntegerField(),
)


# Audit log: bilet timeline için TicketHistory + sistem geneli AuditLog'a yazar.
def log_ticket_action(ticket, actor, action, request=None,
                      action_type=TicketActionType.OTHER):
    TicketHistory.objects.create(
        ticket=ticket, actor=actor, action=action, action_type=action_type,
    )
    audit_log(
        request, AuditCategory.TICKET, action,
        actor=actor, ticket=ticket,
        department=ticket.department if ticket else None,
        target=ticket,
    )


# Bilet listeleme - Rol bazlı filtreleme + sıralama
class TicketListView(LoginRequiredMixin, ListView):
    model = Ticket
    template_name = 'tickets/ticket_list.html'
    context_object_name = 'tickets'
    paginate_by = 20

    def get_queryset(self):
        user = self.request.user
        qs = Ticket.objects.select_related(
            'sender', 'assigned_to', 'department', 'category',
        ).prefetch_related('tags')

        if user.role == Role.ADMIN:
            pass
        elif user.role in (Role.AGENT, Role.MANAGER):
            if user.department_id:
                qs = qs.filter(Q(department=user.department) | Q(sender=user))
            else:
                qs = qs.filter(sender=user)
        else:
            qs = qs.filter(sender=user)

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(subject__icontains=q) | Q(message__icontains=q))

        status_filter = self.request.GET.get('status')
        if status_filter and status_filter in dict(Status.choices):
            qs = qs.filter(status=status_filter)

        priority_filter = self.request.GET.get('priority')
        if priority_filter and priority_filter in dict(Priority.choices):
            qs = qs.filter(priority=priority_filter)

        department_filter = self.request.GET.get('department')
        if department_filter and department_filter.isdigit():
            qs = qs.filter(department_id=int(department_filter))

        category_filter = self.request.GET.get('category')
        if category_filter and category_filter.isdigit():
            qs = qs.filter(category_id=int(category_filter))

        sender_filter = self.request.GET.get('sender')
        if sender_filter and sender_filter.isdigit():
            qs = qs.filter(sender_id=int(sender_filter))

        assigned_filter = self.request.GET.get('assigned_to')
        if assigned_filter and assigned_filter.isdigit():
            qs = qs.filter(assigned_to_id=int(assigned_filter))

        tag_filter = self.request.GET.get('tag')
        if tag_filter and tag_filter.isdigit():
            qs = qs.filter(tags__id=int(tag_filter)).distinct()

        if self.request.GET.get('overdue') == '1':
            qs = qs.exclude(
                status__in=[Status.RESOLVED, Status.CLOSED, Status.ESCALATED]
            ).filter(sla_due_at__lt=timezone.now())

        date_from = self.request.GET.get('date_from')
        if date_from:
            try:
                qs = qs.filter(created_at__date__gte=_date.fromisoformat(date_from))
            except ValueError:
                pass
        date_to = self.request.GET.get('date_to')
        if date_to:
            try:
                qs = qs.filter(created_at__date__lte=_date.fromisoformat(date_to))
            except ValueError:
                pass

        if self.request.GET.get('sla_breach') == '1':
            qs = qs.filter(
                status=Status.CLOSED, closed_at__isnull=False,
                sla_due_at__isnull=False, closed_at__gt=F('sla_due_at'),
            )

        if self.request.GET.get('reopened') == '1':
            qs = qs.filter(reopen_count__gt=0)

        sort = self.request.GET.get('sort', '-created_at')
        if sort == 'priority':
            qs = qs.annotate(_priority_rank=PRIORITY_ORDER).order_by('-_priority_rank', '-created_at')
        else:
            allowed_sorts = {
                'created_at': 'created_at',
                '-created_at': '-created_at',
                'status': 'status',
                'subject': 'subject',
            }
            qs = qs.order_by(allowed_sorts.get(sort, '-created_at'))

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from departments.models import Department, Category

        user = self.request.user
        context['user_role'] = user.role
        context['status_choices'] = Status.choices
        context['priority_choices'] = Priority.choices
        context['current_q'] = self.request.GET.get('q', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['current_priority'] = self.request.GET.get('priority', '')
        context['current_department'] = self.request.GET.get('department', '')
        context['current_category'] = self.request.GET.get('category', '')
        context['current_sender'] = self.request.GET.get('sender', '')
        context['current_assigned_to'] = self.request.GET.get('assigned_to', '')
        context['current_tag'] = self.request.GET.get('tag', '')
        context['current_overdue'] = self.request.GET.get('overdue', '')
        context['tags'] = Tag.objects.all().order_by('name')
        context['current_sort'] = self.request.GET.get('sort', '-created_at')
        context['can_bulk_action'] = user.role in (Role.MANAGER, Role.ADMIN)
        context['priority_choices'] = Priority.choices

        if user.role == Role.ADMIN:
            context['departments'] = Department.objects.order_by('name')
            context['categories'] = (
                Category.objects
                .select_related('department')
                .order_by('department__name', 'name')
            )
            base_users = (
                UserModel.objects
                .filter(is_active=True)
                .select_related('department')
                .order_by('department__name', 'first_name', 'last_name', 'username')
            )
            context['filter_users'] = base_users
            context['assignee_users'] = base_users.filter(role=Role.AGENT)
        elif user.role in (Role.AGENT, Role.MANAGER):
            context['categories'] = (
                Category.objects
                .select_related('department')
                .filter(department=user.department)
                .order_by('name')
            )
            base_users = (
                UserModel.objects
                .filter(is_active=True, department=user.department)
                .select_related('department')
                .order_by('first_name', 'last_name', 'username')
            )
            context['filter_users'] = base_users
            context['assignee_users'] = base_users.filter(role=Role.AGENT)
        else:
            context['departments'] = Department.objects.order_by('name')
            context['categories'] = (
                Category.objects
                .select_related('department')
                .order_by('department__name', 'name')
            )
        return context


TICKET_CREATE_LIMIT_PER_HOUR = 30


def _user_can_create_ticket(user):
    from django.core.cache import cache
    from django.utils import timezone
    now = timezone.now()
    bucket = now.strftime('%Y%m%d%H')
    key = f'ticket_create:{user.pk}:{bucket}'
    count = cache.get(key, 0)
    if count >= TICKET_CREATE_LIMIT_PER_HOUR:
        return False
    cache.set(key, count + 1, timeout=3600)
    return True


# Yeni bilet oluşturma - sender otomatik atanır
class TicketCreateView(LoginRequiredMixin, CreateView):
    model = Ticket
    template_name = 'tickets/ticket_form.html'
    fields = ['subject', 'message', 'department', 'category', 'priority', 'tags']
    success_url = reverse_lazy('tickets:ticket_list')

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if user.role in (Role.AGENT, Role.MANAGER) and user.department_id:
            initial['department'] = user.department_id
        return initial

    def form_valid(self, form):
        if not _user_can_create_ticket(self.request.user):
            messages.error(
                self.request,
                f'Saatlik bilet oluşturma sınırına ulaştınız ({TICKET_CREATE_LIMIT_PER_HOUR}/saat). '
                'Lütfen biraz sonra tekrar deneyin.',
            )
            return self.form_invalid(form)

        category = form.cleaned_data.get('category')
        department = form.cleaned_data.get('department')
        if category and department and category.department_id != department.pk:
            form.add_error('category', 'Seçilen kategori bu departmana ait değil.')
            return self.form_invalid(form)

        form.instance.sender = self.request.user
        form.instance.status = Status.OPEN
        response = super().form_valid(form)

        _save_ticket_attachments(self.request, self.object)

        log_ticket_action(self.object, self.request.user, 'Bilet oluşturuldu.',
                          action_type=TicketActionType.CREATED)

        assignee = self.object.auto_assign()
        if assignee:
            log_ticket_action(
                self.object, None,
                f'Bilet otomatik olarak {assignee.get_full_name() or assignee.username} '
                f'personeline atandı (en az iş yükü).',
                action_type=TicketActionType.ASSIGNED,
            )
            Notification.objects.create(
                recipient=assignee, ticket=self.object,
                message=(
                    f'"{self.object.subject}" (#{self.object.pk}) bileti '
                    f'otomatik olarak size atandı.'
                ),
            )
            if self.object.sender_id != assignee.pk:
                Notification.objects.create(
                    recipient=self.object.sender, ticket=self.object,
                    message=(
                        f'Talebiniz "{self.object.subject}" (#{self.object.pk}) '
                        f'{assignee.get_full_name() or assignee.username} personeline atandı.'
                    ),
                )
        else:
            _notify_department_on_new_ticket(self.object, exclude_user=self.request.user)

        messages.success(
            self.request,
            f'Talebiniz başarıyla oluşturuldu. ({self.object.code})',
        )
        return response


# Çoklu dosya ekini request.FILES'tan alıp TicketAttachment olarak kaydet
def _save_ticket_attachments(request, ticket):
    files = request.FILES.getlist('attachments')
    for f in files:
        TicketAttachment.objects.create(
            ticket=ticket, file=f, uploaded_by=request.user,
        )


# Departmandaki AGENT + MANAGER ekibine tek mesajla bildirim gönderen ortak helper.
def _notify_department_team(ticket, message, exclude_user=None):
    if not ticket.department_id:
        return
    recipients = UserModel.objects.filter(
        department_id=ticket.department_id,
        role__in=[Role.AGENT, Role.MANAGER],
        is_active=True,
    )
    if exclude_user:
        recipients = recipients.exclude(pk=exclude_user.pk)
    Notification.objects.bulk_create([
        Notification(recipient=r, ticket=ticket, message=message)
        for r in recipients
    ])


# Yeni bilet açıldığında departman yöneticisi ve ajanlarına bildirim gönder
def _notify_department_on_new_ticket(ticket, exclude_user=None):
    full_name = (
        ticket.sender.get_full_name() or ticket.sender.username
    ) if ticket.sender else 'Sistem'
    _notify_department_team(
        ticket,
        f'Departmanınıza yeni bir bilet düştü: "{ticket.subject}" (#{ticket.pk}) — {full_name}',
        exclude_user=exclude_user,
    )


# Bilet bir departmandan ayrıldığında, eski departman yöneticisi ve ajanlarına bildirim
def _notify_department_on_ticket_left(ticket, old_department, exclude_user=None):
    if not old_department:
        return
    recipients = UserModel.objects.filter(
        department_id=old_department.pk,
        role__in=[Role.AGENT, Role.MANAGER],
        is_active=True,
    )
    if exclude_user:
        recipients = recipients.exclude(pk=exclude_user.pk)
    Notification.objects.bulk_create([
        Notification(
            recipient=r,
            ticket=ticket,
            message=(
                f'"{ticket.subject}" (#{ticket.pk}) bileti departmanınızdan '
                f'çıkarıldı.'
            ),
        )
        for r in recipients
    ])


# Bilet detay - Rol bazlı erişim kontrolü + geçmiş
class TicketDetailView(LoginRequiredMixin, DetailView):
    model = Ticket
    template_name = 'tickets/ticket_detail.html'
    context_object_name = 'ticket'

    def get_queryset(self):
        user = self.request.user
        qs = Ticket.objects.select_related(
            'sender', 'assigned_to', 'department', 'category',
        ).prefetch_related('tags', 'attachments')

        if user.role == Role.ADMIN:
            return qs
        elif user.role in (Role.AGENT, Role.MANAGER):
            return qs.filter(
                Q(department=user.department) | Q(sender=user)
            )
        else:
            return qs.filter(sender=user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['history'] = self.object.history.select_related('actor').all()
        context['comments'] = self.object.comments.select_related('author').all()

        user = self.request.user
        ticket = self.object
        can_assign = (
            ticket.status not in (Status.RESOLVED, Status.CLOSED, Status.ESCALATED)
            and ticket.department_id is not None
            and (
                user.role == Role.ADMIN
                or (user.role == Role.MANAGER and user.department_id == ticket.department_id)
            )
        )
        context['can_assign'] = can_assign
        if can_assign:
                context['assignable_personnel'] = (
                UserModel.objects
                .filter(department_id=ticket.department_id, role=Role.AGENT, is_active=True)
                .order_by('first_name', 'last_name', 'username')
            )

        context['is_sender'] = (ticket.sender_id == user.pk)
        context['is_assignee'] = (ticket.assigned_to_id == user.pk)
        context['can_resolve'] = (
            ticket.status == Status.IN_PROGRESS
            and (context['is_assignee'] or user.role == Role.ADMIN)
        )
        context['awaiting_confirmation'] = (
            ticket.status == Status.RESOLVED and context['is_sender']
        )
        context['needs_csat'] = (
            ticket.status == Status.CLOSED
            and ticket.csat_rating is None
            and context['is_sender']
        )
        context['csat_choices'] = [1, 2, 3, 4, 5]
        return context


# Talep üstlenme - Personel bileti üzerine alır (OPEN -> IN_PROGRESS)
@login_required
@require_POST
def ticket_take_view(request, pk):
    user = request.user

    if user.role not in (Role.AGENT, Role.MANAGER):
        return HttpResponseForbidden('Bu işlem için yetkiniz bulunmamaktadır.')

    ticket = get_object_or_404(Ticket, pk=pk)

    if ticket.department != user.department:
        return HttpResponseForbidden('Bu bilet sizin departmanınıza ait değildir.')

    if ticket.status != Status.OPEN:
        messages.warning(request, 'Bu bilet zaten işlemde veya kapalı durumda.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    ticket.take_into_process(personnel=user)
    log_ticket_action(ticket, user, f'{user.get_full_name() or user.username} bileti üstlendi.',
                      action_type=TicketActionType.TAKEN)

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

    messages.success(request, f'Bilet #{ticket.pk} başarıyla üstlenildi.')
    return redirect('tickets:ticket_detail', pk=ticket.pk)


# Manuel atama — Admin tüm departmanlara, Manager kendi departmanına AGENT atayabilir.
@login_required
@require_POST
def ticket_assign_view(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    user = request.user

    is_admin = (user.role == Role.ADMIN)
    is_dept_manager = (
        user.role == Role.MANAGER
        and ticket.department_id == user.department_id
    )
    if not (is_admin or is_dept_manager):
        return HttpResponseForbidden('Bu bilete atama yapma yetkiniz yok.')

    if ticket.status in (Status.RESOLVED, Status.CLOSED, Status.ESCALATED):
        messages.warning(request, 'Bu durumdaki biletler için atama yapılamaz.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    if not ticket.department_id:
        messages.error(request, 'Bu biletin bir departmanı yok; önce transfer edin.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    personnel_id = request.POST.get('personnel_id', '')

    if not personnel_id:
        old_assignee = ticket.assigned_to
        with transaction.atomic():
            ticket.assigned_to = None
            ticket.status = Status.OPEN
            ticket.save(update_fields=['assigned_to', 'status', 'updated_at'])
            log_ticket_action(
                ticket, user,
                'Atama kaldırıldı'
                + (f' ({old_assignee.get_full_name() or old_assignee.username})' if old_assignee else ''),
                action_type=TicketActionType.UNASSIGNED,
            )
        if old_assignee and old_assignee != user:
            Notification.objects.create(
                recipient=old_assignee, ticket=ticket,
                message=f'"{ticket.subject}" (#{ticket.pk}) bileti üzerinizden alındı.',
            )
        messages.success(request, f'Bilet #{ticket.pk} ataması kaldırıldı.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    try:
        target = UserModel.objects.get(pk=personnel_id, is_active=True)
    except (UserModel.DoesNotExist, ValueError):
        messages.error(request, 'Geçersiz personel.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    if target.role != Role.AGENT or target.department_id != ticket.department_id:
        messages.error(
            request,
            'Sadece biletin departmanındaki personel rolündeki kullanıcılara atama yapılabilir.',
        )
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    if ticket.assigned_to_id == target.pk:
        messages.info(request, 'Bilet zaten bu personele atanmış.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    old_assignee = ticket.assigned_to
    with transaction.atomic():
        ticket.assigned_to = target
        ticket.status = Status.IN_PROGRESS
        ticket.save(update_fields=['assigned_to', 'status', 'updated_at'])
        log_ticket_action(
            ticket, user,
            f'Bilet {target.get_full_name() or target.username} personeline atandı.',
            action_type=TicketActionType.ASSIGNED,
        )

    Notification.objects.create(
        recipient=target, ticket=ticket,
        message=(
            f'"{ticket.subject}" (#{ticket.pk}) bileti size atandı '
            f'({user.get_full_name() or user.username} tarafından).'
        ),
    )
    if ticket.sender and ticket.sender != target:
        Notification.objects.create(
            recipient=ticket.sender, ticket=ticket,
            message=(
                f'Talebiniz "{ticket.subject}" (#{ticket.pk}) '
                f'{target.get_full_name() or target.username} kişisine atandı.'
            ),
        )
    if old_assignee and old_assignee != target and old_assignee != user:
        Notification.objects.create(
            recipient=old_assignee, ticket=ticket,
            message=f'"{ticket.subject}" (#{ticket.pk}) bileti üzerinizden alındı.',
        )

    messages.success(
        request,
        f'Bilet #{ticket.pk}, "{target.get_full_name() or target.username}" kişisine atandı.',
    )
    return redirect('tickets:ticket_detail', pk=ticket.pk)


# Çözüldü işaretleme — atanan personel veya Admin (IN_PROGRESS -> RESOLVED, onay bekler).
@login_required
@require_POST
def ticket_resolve_view(request, pk):
    user = request.user
    ticket = get_object_or_404(Ticket, pk=pk)

    is_assigned = (ticket.assigned_to == user)
    is_admin = (user.role == Role.ADMIN)

    if not (is_assigned or is_admin):
        return HttpResponseForbidden(
            'Sadece bileti üstlenen personel veya Admin çözüm işaretleyebilir.'
        )

    if ticket.status != Status.IN_PROGRESS:
        messages.warning(request, 'Sadece "İşlemde" durumundaki biletler çözüldü olarak işaretlenebilir.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    resolution_note = request.POST.get('resolution_note', '').strip()
    if not resolution_note:
        messages.error(request, 'Çözüm notu zorunludur.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    ticket.mark_resolved(resolution_note=resolution_note)
    log_ticket_action(
        ticket, user,
        f'Bilet çözüldü olarak işaretlendi. Çözüm: {resolution_note[:100]}',
        action_type=TicketActionType.RESOLVED,
    )

    if ticket.sender:
        Notification.objects.create(
            recipient=ticket.sender,
            ticket=ticket,
            message=(
                f'Talebiniz "{ticket.subject}" (#{ticket.pk}) çözüldü olarak işaretlendi. '
                f'Lütfen sorunun giderildiğini onaylayın (3 gün içinde yanıt verilmezse otomatik kapanır).'
            ),
        )

    messages.success(request, f'Bilet #{ticket.pk} çözüldü olarak işaretlendi; talep sahibinin onayı bekleniyor.')
    return redirect('tickets:ticket_detail', pk=ticket.pk)


# Bilet transfer -- Başka departmana aktarma (AGENT/MANAGER/ADMIN)
@login_required
def ticket_transfer_view(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    user = request.user

    if user.role not in (Role.AGENT, Role.MANAGER, Role.ADMIN):
        return HttpResponseForbidden('Bu işlem için yetkiniz bulunmamaktadır.')

    if user.role in (Role.AGENT, Role.MANAGER):
        if ticket.department != user.department:
            return HttpResponseForbidden('Bu bilet sizin departmanınıza ait değildir.')

    if ticket.status in (Status.RESOLVED, Status.CLOSED, Status.ESCALATED):
        messages.warning(request, 'Bu durumdaki biletler transfer edilemez.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    if request.method == 'GET':
        from departments.models import Department
        departments = Department.objects.exclude(pk=ticket.department_id)
        return render(request, 'tickets/ticket_transfer.html', {
            'ticket': ticket,
            'departments': departments,
        })

    from departments.models import Department, Category
    new_dept_id = request.POST.get('department')
    new_cat_id = request.POST.get('category') or None

    new_department = get_object_or_404(Department, pk=new_dept_id)
    new_category = None
    if new_cat_id:
        new_category = get_object_or_404(Category, pk=new_cat_id, department=new_department)

    old_department = ticket.department
    old_assigned_to = ticket.assigned_to
    ticket.transfer(new_department, new_category)
    log_ticket_action(
        ticket, user,
        f'Bilet {old_department.name if old_department else "?"} -> {new_department.name} departmanına transfer edildi.',
        action_type=TicketActionType.TRANSFERRED,
    )

    if ticket.sender:
        Notification.objects.create(
            recipient=ticket.sender,
            ticket=ticket,
            message=(
                f'Talebiniz "{ticket.subject}" (#{ticket.pk}) '
                f'{new_department.name} departmanına transfer edilmiştir.'
            ),
        )

    if old_assigned_to and old_assigned_to != user:
        Notification.objects.create(
            recipient=old_assigned_to,
            ticket=ticket,
            message=(
                f'Üstlendiğiniz bilet "{ticket.subject}" (#{ticket.pk}) '
                f'{new_department.name} departmanına transfer edildi.'
            ),
        )

    assignee = ticket.auto_assign()
    if assignee:
        log_ticket_action(
            ticket, None,
            f'Bilet otomatik olarak {assignee.get_full_name() or assignee.username} '
            f'personeline atandı (en az iş yükü).',
            action_type=TicketActionType.ASSIGNED,
        )
        Notification.objects.create(
            recipient=assignee, ticket=ticket,
            message=f'"{ticket.subject}" (#{ticket.pk}) bileti otomatik olarak size atandı.',
        )
    else:
        _notify_department_on_new_ticket(ticket, exclude_user=user)
    _notify_department_on_ticket_left(ticket, old_department, exclude_user=user)

    messages.success(
        request,
        f'Bilet #{ticket.pk} "{new_department.name}" departmanına transfer edildi.',
    )

    if user.role != Role.ADMIN and ticket.sender != user:
        return redirect('tickets:ticket_list')

    return redirect('tickets:ticket_detail', pk=ticket.pk)


# Bilet güncelleme — Sadece talep sahibi (OPEN durumdayken)
class TicketUpdateView(LoginRequiredMixin, UpdateView):
    model = Ticket
    template_name = 'tickets/ticket_form.html'
    fields = ['subject', 'message', 'department', 'category', 'priority', 'tags']

    def get_queryset(self):
        user = self.request.user
        qs = Ticket.objects.select_related('department', 'category')

        if user.role == Role.ADMIN:
            return qs
        return qs.filter(sender=user, status=Status.OPEN, assigned_to__isnull=True)

    def get_success_url(self):
        return reverse_lazy('tickets:ticket_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        category = form.cleaned_data.get('category')
        department = form.cleaned_data.get('department')
        if category and department and category.department_id != department.pk:
            form.add_error('category', 'Seçilen kategori bu departmana ait değil.')
            return self.form_invalid(form)

        response = super().form_valid(form)
        _save_ticket_attachments(self.request, self.object)
        log_ticket_action(self.object, self.request.user, 'Bilet güncellendi.',
                          action_type=TicketActionType.UPDATED)
        messages.success(self.request, f'{self.object.code} başarıyla güncellendi.')
        return response


# Bilet yorum ekleme — Talep sahibi veya ilgili personel
@login_required
@require_POST
def ticket_add_comment_view(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    user = request.user

    if user.role == Role.ADMIN:
        pass
    elif user.role in (Role.AGENT, Role.MANAGER):
        if ticket.department != user.department and ticket.sender != user:
            return HttpResponseForbidden('Bu bilete yorum yapamazsınız.')
    elif ticket.sender != user:
        return HttpResponseForbidden('Bu bilete yorum yapamazsınız.')

    content = request.POST.get('content', '').strip()
    attachment = request.FILES.get('comment_attachment')

    if not content and not attachment:
        messages.warning(request, 'Mesaj veya dosya eklerinden en az birini gönderin.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    if len(content) > 2000:
        messages.warning(request, 'Yorum en fazla 2000 karakter olabilir.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    TicketComment.objects.create(
        ticket=ticket, author=user, content=content,
        attachment=attachment,
    )

    if user == ticket.sender:
        recipient = ticket.assigned_to
    else:
        recipient = ticket.sender

    if recipient:
        Notification.objects.create(
            recipient=recipient,
            ticket=ticket,
            message=(
                f'"{ticket.subject}" (#{ticket.pk}) biletine '
                f'{user.get_full_name() or user.username} mesaj attı.'
            ),
        )

    return redirect('tickets:ticket_detail', pk=ticket.pk)


# Çözüm onayı — Talep sahibi RESOLVED biletini onaylar (-> CLOSED).
@login_required
@require_POST
def ticket_confirm_resolution_view(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    user = request.user

    if ticket.sender != user:
        return HttpResponseForbidden('Sadece talep sahibi çözüm onayı verebilir.')

    if ticket.status != Status.RESOLVED:
        messages.warning(request, 'Bu işlem sadece "Çözüldü" durumundaki biletler için geçerlidir.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    with transaction.atomic():
        ticket.confirm_resolution()
        log_ticket_action(
            ticket, user, 'Talep sahibi sorununun çözüldüğünü onayladı; bilet kapatıldı.',
            action_type=TicketActionType.RESOLUTION_CONFIRMED,
        )

    _notify_department_team(
        ticket,
        f'"{ticket.subject}" (#{ticket.pk}) bileti talep sahibi tarafından onaylandı ve kapatıldı.',
        exclude_user=user,
    )

    messages.success(request, 'Onayınız kaydedildi. Lütfen kısa bir memnuniyet puanı verin.')
    return redirect('tickets:ticket_detail', pk=ticket.pk)


# Çözüm reddi (gerekçe zorunlu) — MAX_REOPENS altında IN_PROGRESS'e döner, aşılınca ESCALATED.
@login_required
@require_POST
def ticket_reject_resolution_view(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    user = request.user

    if ticket.sender != user:
        return HttpResponseForbidden('Sadece talep sahibi çözüm reddi verebilir.')

    if ticket.status != Status.RESOLVED:
        messages.warning(request, 'Bu işlem sadece "Çözüldü" durumundaki biletler için geçerlidir.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    reason = request.POST.get('reason', '').strip()
    if not reason:
        messages.error(request, 'Red gerekçesi zorunludur.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)
    if len(reason) > 1000:
        reason = reason[:1000]

    with transaction.atomic():
        reopened = ticket.reject_resolution(reason)
        if reopened:
            log_ticket_action(
                ticket, user,
                f'Talep sahibi çözümü reddetti (#{ticket.reopen_count}/{2}). Gerekçe: {reason[:120]}',
                action_type=TicketActionType.RESOLUTION_REJECTED,
            )
        else:
            log_ticket_action(
                ticket, user,
                f'Çözüm 3. kez reddedildi; bilet eskalasyona alındı. Gerekçe: {reason[:120]}',
                action_type=TicketActionType.ESCALATED,
            )

    if reopened:
        msg = (
            f'"{ticket.subject}" (#{ticket.pk}) bileti talep sahibi tarafından '
            f'çözümsüz olarak işaretlendi ve yeniden işleme alındı. Gerekçe: {reason[:120]}'
        )
    else:
        msg = (
            f'"{ticket.subject}" (#{ticket.pk}) bileti 3. kez reddedildi ve '
            f'ESKALASYON\'a alındı. Lütfen yönetici müdahalesi sağlayın. Gerekçe: {reason[:120]}'
        )
    _notify_department_team(ticket, msg)

    if reopened:
        messages.warning(
            request,
            f'Sorununuzun devam ettiğini kaydettik. Biletiniz yeniden işleme alındı '
            f'(kalan red hakkı: {2 - ticket.reopen_count}).',
        )
    else:
        messages.error(
            request,
            'Bilet 3. kez reddedildiği için eskalasyona alındı. Yönetici müdahalesi sağlanacaktır.',
        )

    return redirect('tickets:ticket_detail', pk=ticket.pk)


# CSAT — Bilet CLOSED'a geçtikten sonra talep sahibi 1-5 arası puan verir
@login_required
@require_POST
def ticket_rate_csat_view(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    user = request.user

    if ticket.sender != user:
        return HttpResponseForbidden('Sadece talep sahibi puan verebilir.')

    if ticket.status != Status.CLOSED:
        messages.warning(request, 'Sadece kapanmış biletler puanlanabilir.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    if ticket.csat_rating is not None:
        messages.info(request, 'Bu bilet için zaten puan verilmiş.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    raw = request.POST.get('rating', '').strip()
    if not raw.isdigit():
        messages.error(request, 'Geçersiz puan.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)
    rating = int(raw)
    if rating < 1 or rating > 5:
        messages.error(request, 'Puan 1 ile 5 arasında olmalıdır.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    ticket.set_csat(rating)
    log_ticket_action(
        ticket, user, f'Memnuniyet puanı verildi: {rating}/5',
        action_type=TicketActionType.CSAT_RATED,
    )

    messages.success(request, f'Puanınız ({rating}/5) için teşekkür ederiz.')
    return redirect('tickets:ticket_detail', pk=ticket.pk)


# Bilet yeniden açma (kilit override): Admin her kilitli, Manager kendi dept. ESCALATED'ı.
@login_required
@require_POST
def ticket_reopen_view(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    user = request.user

    is_admin = user.role == Role.ADMIN
    is_dept_manager = (
        user.role == Role.MANAGER and ticket.department_id == user.department_id
    )
    if not (is_admin or is_dept_manager):
        return HttpResponseForbidden('Bu bileti yeniden açma yetkiniz bulunmamaktadır.')

    allowed = (Status.CLOSED, Status.ESCALATED) if is_admin else (Status.ESCALATED,)
    if ticket.status not in allowed:
        if is_admin:
            messages.warning(request, 'Sadece kilitli (Kapalı veya Eskalasyon) biletler yeniden açılabilir.')
        else:
            messages.warning(request, 'Yönetici olarak yalnızca eskalasyona alınmış biletleri yeniden açabilirsiniz.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    ticket.reopen()
    log_ticket_action(ticket, user, 'Bilet yeniden açıldı.',
                      action_type=TicketActionType.REOPENED)

    _notify_department_team(
        ticket,
        f'"{ticket.subject}" (#{ticket.pk}) bileti yeniden açıldı.',
        exclude_user=user,
    )

    messages.success(request, f'Bilet #{ticket.pk} yeniden açıldı.')
    return redirect('tickets:ticket_detail', pk=ticket.pk)


# Toplu bilet işlemi — Admin / Manager (kapsamlarına göre)
@login_required
@require_POST
def ticket_bulk_action_view(request):
    user = request.user
    if user.role not in (Role.MANAGER, Role.ADMIN):
        return HttpResponseForbidden('Bu işlem için yetkiniz bulunmamaktadır.')

    action = request.POST.get('action', '')
    ticket_ids = request.POST.getlist('ticket_ids')
    if not ticket_ids:
        messages.warning(request, 'Lütfen en az bir bilet seçin.')
        return redirect('tickets:ticket_list')

    qs = Ticket.objects.filter(pk__in=ticket_ids)
    if user.role == Role.MANAGER:
        qs = qs.filter(department=user.department)

    if action == 'resolve':
        from django.utils import timezone
        target = qs.filter(status=Status.IN_PROGRESS)
        ids = list(target.values_list('pk', flat=True))
        count = target.update(
            status=Status.RESOLVED,
            resolved_at=timezone.now(),
            resolution_note='Toplu işlem ile çözüldü olarak işaretlendi.',
            resolution_confirmed=None,
            closed_at=None,
        )
        for tid in ids:
            TicketHistory.objects.create(
                ticket_id=tid, actor=user,
                action='Bilet çözüldü olarak işaretlendi (toplu işlem).',
                action_type=TicketActionType.RESOLVED,
            )
        for t in Ticket.objects.filter(pk__in=ids).select_related('sender'):
            if t.sender:
                Notification.objects.create(
                    recipient=t.sender, ticket=t,
                    message=(
                        f'Talebiniz "{t.subject}" (#{t.pk}) çözüldü olarak işaretlendi. '
                        f'Lütfen onaylayın (3 gün içinde otomatik kapanır).'
                    ),
                )
        messages.success(request, f'{count} bilet çözüldü olarak işaretlendi.')

    elif action == 'reopen':
        if user.role == Role.ADMIN:
            target = qs.filter(status__in=[Status.CLOSED, Status.ESCALATED])
        else:
            target = qs.filter(status=Status.ESCALATED)
        ids = list(target.values_list('pk', flat=True))
        count = target.update(
            status=Status.OPEN, assigned_to=None, closed_at=None,
            resolved_at=None, resolution_confirmed=None,
            reopen_count=0, rejection_reason='', escalated_at=None,
        )
        for tid in ids:
            TicketHistory.objects.create(
                ticket_id=tid, actor=user, action='Bilet yeniden açıldı (toplu işlem).',
                action_type=TicketActionType.REOPENED,
            )
        messages.success(request, f'{count} bilet yeniden açıldı.')

    elif action == 'delete':
        count = qs.count()
        qs.delete()
        messages.success(request, f'{count} bilet silindi.')

    elif action.startswith('priority:'):
        new_priority = action.split(':', 1)[1]
        if new_priority not in dict(Priority.choices):
            messages.error(request, 'Geçersiz öncelik.')
            return redirect('tickets:ticket_list')
        from .models import SLA_HOURS, add_business_hours
        affected = list(qs)
        count = qs.update(priority=new_priority)
        for t in affected:
            if t.created_at:
                t.sla_due_at = add_business_hours(
                    t.created_at, SLA_HOURS.get(new_priority, SLA_HOURS[Priority.NORMAL])
                )
        Ticket.objects.bulk_update(affected, ['sla_due_at'], batch_size=500)
        messages.success(request, f'{count} biletin önceliği "{dict(Priority.choices)[new_priority]}" olarak ayarlandı.')

    else:
        messages.error(request, 'Geçersiz işlem.')

    return redirect('tickets:ticket_list')


# Bilet eki silme — Yükleyen, talep sahibi veya ilgili Manager/Admin
@login_required
@require_POST
def ticket_attachment_delete_view(request, pk):
    attachment = get_object_or_404(TicketAttachment.objects.select_related('ticket'), pk=pk)
    ticket = attachment.ticket
    user = request.user

    is_uploader = (attachment.uploaded_by == user)
    is_sender_before_assign = (ticket.sender == user and ticket.assigned_to is None)
    is_owner = is_uploader or is_sender_before_assign
    is_admin = user.role == Role.ADMIN
    is_dept_manager = (
        user.role == Role.MANAGER and ticket.department_id == user.department_id
    )

    if not (is_owner or is_admin or is_dept_manager):
        return HttpResponseForbidden('Bu eki silme yetkiniz yok.')

    attachment.delete()
    messages.info(request, 'Dosya eki silindi.')
    return redirect('tickets:ticket_detail', pk=ticket.pk)


# Bilet silme — Talep sahibi (OPEN), ilgili Manager veya Admin
@login_required
@require_POST
def ticket_delete_view(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    user = request.user

    is_sender_open = (ticket.sender == user and ticket.status == Status.OPEN)
    is_admin = (user.role == Role.ADMIN)
    is_dept_manager = (
        user.role == Role.MANAGER
        and ticket.department == user.department
    )

    if not (is_sender_open or is_admin or is_dept_manager):
        return HttpResponseForbidden(
            'Sadece talep sahibi (açık biletler), ilgili yönetici veya Admin silebilir.'
        )

    ticket_pk = ticket.pk
    ticket.delete()

    messages.success(request, f'Bilet #{ticket_pk} başarıyla silindi.')
    return redirect('tickets:ticket_list')


# Kanban görünümü — Açık / İşlemde / Kapalı kolonları (rol bazlı kapsam)
class KanbanView(LoginRequiredMixin, TemplateView):
    template_name = 'tickets/kanban.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        qs = Ticket.objects.select_related(
            'sender', 'assigned_to', 'department', 'category',
        ).prefetch_related('tags')

        if user.role == Role.ADMIN:
            pass
        elif user.role in (Role.AGENT, Role.MANAGER):
            if user.department_id:
                qs = qs.filter(Q(department=user.department) | Q(sender=user))
            else:
                qs = qs.filter(sender=user)
        else:
            qs = qs.filter(sender=user)

        from django.utils import timezone
        from datetime import timedelta
        closed_cutoff = timezone.now() - timedelta(days=30)

        context['open_tickets'] = qs.filter(status=Status.OPEN).order_by('-created_at')[:100]
        context['in_progress_tickets'] = qs.filter(status=Status.IN_PROGRESS).order_by('-updated_at')[:100]
        context['resolved_tickets'] = qs.filter(status=Status.RESOLVED).order_by('-resolved_at')[:100]
        context['closed_tickets'] = qs.filter(
            status=Status.CLOSED, closed_at__gte=closed_cutoff,
        ).order_by('-closed_at')[:50]
        context['escalated_tickets'] = qs.filter(status=Status.ESCALATED).order_by('-escalated_at')[:50]
        context['user_role'] = user.role
        context['user_dept_id'] = user.department_id
        return context


# AJAX kanban drop
@login_required
def ticket_change_status_view(request, pk):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Sadece POST.'}, status=405)

    ticket = get_object_or_404(Ticket, pk=pk)
    user = request.user
    target = request.POST.get('status', '')

    if target not in dict(Status.choices):
        return JsonResponse({'ok': False, 'error': 'Geçersiz durum.'}, status=400)

    if target == Status.IN_PROGRESS and ticket.status == Status.OPEN:
        if user.role not in (Role.AGENT, Role.MANAGER) or ticket.department_id != user.department_id:
            return JsonResponse({'ok': False, 'error': 'Bu departmandan değilsiniz.'}, status=403)
        ticket.take_into_process(personnel=user)
        log_ticket_action(ticket, user, f'{user.get_full_name() or user.username} bileti üstlendi.',
                          action_type=TicketActionType.TAKEN)
        if ticket.sender:
            Notification.objects.create(
                recipient=ticket.sender, ticket=ticket,
                message=f'Talebiniz "{ticket.subject}" (#{ticket.pk}) işleme alındı.',
            )
        return JsonResponse({'ok': True, 'status': ticket.status})

    if target == Status.RESOLVED and ticket.status == Status.IN_PROGRESS:
        if not (ticket.assigned_to == user or user.role == Role.ADMIN):
            return JsonResponse({'ok': False, 'error': 'Bileti üstlenen veya Admin çözüm işaretleyebilir.'}, status=403)
        note = request.POST.get('resolution_note', '').strip()
        if not note:
            return JsonResponse({'ok': False, 'error': 'Çözüm notu zorunludur.'}, status=400)
        ticket.mark_resolved(resolution_note=note)
        log_ticket_action(ticket, user, f'Bilet çözüldü olarak işaretlendi. Çözüm: {note[:100]}',
                          action_type=TicketActionType.RESOLVED)
        if ticket.sender:
            Notification.objects.create(
                recipient=ticket.sender, ticket=ticket,
                message=(
                    f'Talebiniz "{ticket.subject}" (#{ticket.pk}) çözüldü olarak işaretlendi. '
                    f'Lütfen onaylayın (3 gün içinde otomatik kapanır).'
                ),
            )
        return JsonResponse({'ok': True, 'status': ticket.status})

    if target == Status.OPEN and ticket.status in (Status.CLOSED, Status.ESCALATED):
        if user.role != Role.ADMIN:
            return JsonResponse({'ok': False, 'error': 'Sadece Admin kilitlenmiş bileti yeniden açabilir.'}, status=403)
        ticket.reopen()
        log_ticket_action(ticket, user, 'Bilet yeniden açıldı.',
                          action_type=TicketActionType.REOPENED)
        return JsonResponse({'ok': True, 'status': ticket.status})

    return JsonResponse({'ok': False, 'error': 'Geçersiz durum geçişi.'}, status=400)



TAG_COLOR_PALETTE = [
    ('#dc3545', 'Kırmızı'),
    ('#fd7e14', 'Turuncu'),
    ('#ffc107', 'Sarı'),
    ('#198754', 'Yeşil'),
    ('#20c997', 'Turkuaz'),
    ('#0dcaf0', 'Açık Mavi'),
    ('#0d6efd', 'Mavi'),
    ('#6610f2', 'Mor'),
    ('#d63384', 'Pembe'),
    ('#6c757d', 'Gri'),
    ('#212529', 'Siyah'),
    ('#adb5bd', 'Açık Gri'),
]


class TagListView(AdminRequiredMixin, ListView):
    model = Tag
    template_name = 'tickets/tag_list.html'
    context_object_name = 'tags'


class TagCreateView(AdminRequiredMixin, CreateView):
    model = Tag
    template_name = 'tickets/tag_form.html'
    fields = ['name', 'color']
    success_url = reverse_lazy('tickets:tag_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['color_palette'] = TAG_COLOR_PALETTE
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        audit_log(self.request, AuditCategory.OTHER, f'Etiket oluşturuldu: {self.object.name}', target=self.object)
        messages.success(self.request, f'"{self.object.name}" etiketi başarıyla oluşturuldu.')
        return response


class TagUpdateView(AdminRequiredMixin, UpdateView):
    model = Tag
    template_name = 'tickets/tag_form.html'
    fields = ['name', 'color']
    success_url = reverse_lazy('tickets:tag_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['color_palette'] = TAG_COLOR_PALETTE
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        audit_log(self.request, AuditCategory.OTHER, f'Etiket güncellendi: {self.object.name}', target=self.object)
        messages.success(self.request, f'"{self.object.name}" etiketi başarıyla güncellendi.')
        return response


class TagDeleteView(AdminRequiredMixin, DeleteView):
    model = Tag
    template_name = 'tickets/tag_confirm_delete.html'
    success_url = reverse_lazy('tickets:tag_list')

    def form_valid(self, form):
        tag_name = self.object.name
        response = super().form_valid(form)
        audit_log(self.request, AuditCategory.OTHER, f'Etiket silindi: {tag_name}')
        messages.success(self.request, f'"{tag_name}" etiketi başarıyla silindi.')
        return response
