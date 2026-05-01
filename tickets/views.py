from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from identity.views import AdminRequiredMixin
from django.urls import reverse_lazy
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.db.models import Q, Case, When, IntegerField

from .models import Ticket, Status, Priority, TicketHistory, TicketComment, TicketAttachment, Tag
from notifications.models import Notification
from identity.models import Role
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
        from identity.models import User as UserModel, AuditLog
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


# Önceliklerin sayısal sıralaması (LOW < NORMAL < HIGH < URGENT)
PRIORITY_ORDER = Case(
    When(priority=Priority.URGENT, then=4),
    When(priority=Priority.HIGH, then=3),
    When(priority=Priority.NORMAL, then=2),
    When(priority=Priority.LOW, then=1),
    output_field=IntegerField(),
)


# Audit log yardımcı fonksiyonu — bilet detay timeline'ı için TicketHistory,
# sistem genel "Geçmiş" sayfası için merkezi AuditLog'a yazar.
def log_ticket_action(ticket, actor, action, request=None):
    TicketHistory.objects.create(ticket=ticket, actor=actor, action=action)
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

        # Rol bazlı filtreleme
        # AGENT/MANAGER: kendi departmanının biletleri + kendi açtığı biletler (başka
        # departmana gönderdikleri dahil). Departmanı atanmamış ise sadece kendi biletleri.
        if user.role == Role.ADMIN:
            pass  # Tüm biletler
        elif user.role in (Role.AGENT, Role.MANAGER):
            if user.department_id:
                qs = qs.filter(Q(department=user.department) | Q(sender=user))
            else:
                qs = qs.filter(sender=user)
        else:
            qs = qs.filter(sender=user)

        # Durum filtresi (query string: ?status=OPEN)
        status_filter = self.request.GET.get('status')
        if status_filter and status_filter in dict(Status.choices):
            qs = qs.filter(status=status_filter)

        # Öncelik filtresi (?priority=HIGH)
        priority_filter = self.request.GET.get('priority')
        if priority_filter and priority_filter in dict(Priority.choices):
            qs = qs.filter(priority=priority_filter)

        # Departman filtresi (?department=<id>) — sadece ADMIN için kullanışlı,
        # diğer roller zaten kendi departmanına kısıtlı.
        department_filter = self.request.GET.get('department')
        if department_filter and department_filter.isdigit():
            qs = qs.filter(department_id=int(department_filter))

        # Kategori filtresi (?category=<id>)
        category_filter = self.request.GET.get('category')
        if category_filter and category_filter.isdigit():
            qs = qs.filter(category_id=int(category_filter))

        # Açan (sender) filtresi (?sender=<id>)
        sender_filter = self.request.GET.get('sender')
        if sender_filter and sender_filter.isdigit():
            qs = qs.filter(sender_id=int(sender_filter))

        # Üstlenen/Kapatan (assigned_to) filtresi (?assigned_to=<id>)
        assigned_filter = self.request.GET.get('assigned_to')
        if assigned_filter and assigned_filter.isdigit():
            qs = qs.filter(assigned_to_id=int(assigned_filter))

        # Etiket filtresi (?tag=<id>)
        tag_filter = self.request.GET.get('tag')
        if tag_filter and tag_filter.isdigit():
            qs = qs.filter(tags__id=int(tag_filter)).distinct()

        # Sıralama (?sort=priority / ?sort=status / ?sort=created_at)
        sort = self.request.GET.get('sort', '-created_at')
        if sort == 'priority':
            # Yüksek → düşük sırala (URGENT > HIGH > NORMAL > LOW)
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
        from identity.models import User as UserModel

        user = self.request.user
        context['user_role'] = user.role
        context['status_choices'] = Status.choices
        context['priority_choices'] = Priority.choices
        context['current_status'] = self.request.GET.get('status', '')
        context['current_priority'] = self.request.GET.get('priority', '')
        context['current_department'] = self.request.GET.get('department', '')
        context['current_category'] = self.request.GET.get('category', '')
        context['current_sender'] = self.request.GET.get('sender', '')
        context['current_assigned_to'] = self.request.GET.get('assigned_to', '')
        context['current_tag'] = self.request.GET.get('tag', '')
        context['tags'] = Tag.objects.all().order_by('name')
        context['current_sort'] = self.request.GET.get('sort', '-created_at')
        # Toplu işlem yetkisi (Manager/Admin)
        context['can_bulk_action'] = user.role in (Role.MANAGER, Role.ADMIN)
        context['priority_choices'] = Priority.choices

        # Filtre dropdown'ları için rol bazlı kapsam.
        # Sıralama: önce departman adı, sonra kullanıcı/kategori adı
        # → "IT - Batuhan", "IT - Hakan", "Muhasebe - Ahmet" akışı.
        # filter_users  : Açan dropdown'u (herhangi bir rol bilet açabilir)
        # assignee_users: Üstlenen dropdown'u — sadece AGENT (bilet üstlenebilen rol)
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
            # Sadece kendi departmanlarındaki kategoriler ve personel
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
            # EMPLOYEE: biletlerini departman ve kategoriye göre filtreleyebilsin
            context['departments'] = Department.objects.order_by('name')
            context['categories'] = (
                Category.objects
                .select_related('department')
                .order_by('department__name', 'name')
            )
        return context


# Yeni bilet oluşturma - sender otomatik atanır
class TicketCreateView(LoginRequiredMixin, CreateView):
    model = Ticket
    template_name = 'tickets/ticket_form.html'
    # 'attachment' artık modelin alanı değil; çoklu dosya request.FILES'dan elle alınır
    fields = ['subject', 'message', 'department', 'category', 'priority', 'tags']
    success_url = reverse_lazy('tickets:ticket_list')

    def get_initial(self):
        initial = super().get_initial()
        # AGENT/MANAGER: kendi departmanını otomatik seç → kategori AJAX'ı sayfa yüklendiğinde tetiklenir
        user = self.request.user
        if user.role in (Role.AGENT, Role.MANAGER) and user.department_id:
            initial['department'] = user.department_id
        return initial

    def form_valid(self, form):
        category = form.cleaned_data.get('category')
        department = form.cleaned_data.get('department')
        if category and department and category.department_id != department.pk:
            form.add_error('category', 'Seçilen kategori bu departmana ait değil.')
            return self.form_invalid(form)

        form.instance.sender = self.request.user
        form.instance.status = Status.OPEN
        response = super().form_valid(form)

        # Çoklu dosya ekleri kaydet
        _save_ticket_attachments(self.request, self.object)

        log_ticket_action(self.object, self.request.user, 'Bilet oluşturuldu.')
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
        return context


# Talep üstlenme - Personel bileti üzerine alır (OPEN -> IN_PROGRESS)
@login_required
def ticket_take_view(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden('Sadece POST istekleri kabul edilir.')

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
    log_ticket_action(ticket, user, f'{user.get_full_name() or user.username} bileti üstlendi.')

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


# Talep kapatma - Atanan personel bileti kapatır (IN_PROGRESS -> CLOSED)
@login_required
def ticket_close_view(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden('Sadece POST istekleri kabul edilir.')

    user = request.user
    ticket = get_object_or_404(Ticket, pk=pk)

    is_assigned = (ticket.assigned_to == user)
    is_admin = (user.role == Role.ADMIN)

    if not (is_assigned or is_admin):
        return HttpResponseForbidden(
            'Sadece bileti üstlenen personel veya Admin kapatabilir.'
        )

    if ticket.status != Status.IN_PROGRESS:
        messages.warning(request, 'Sadece "İşlemde" durumundaki biletler kapatılabilir.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    resolution_note = request.POST.get('resolution_note', '')
    ticket.close(resolution_note=resolution_note)
    log_ticket_action(ticket, user, f'Bilet kapatıldı. Çözüm: {resolution_note[:100]}')

    if ticket.sender:
        Notification.objects.create(
            recipient=ticket.sender,
            ticket=ticket,
            message=(
                f'Talebiniz "{ticket.subject}" (#{ticket.pk}) '
                f'çözülmüş ve kapatılmıştır.'
            ),
        )

    messages.success(request, f'Bilet #{ticket.pk} başarıyla kapatıldı.')
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

    if ticket.status == Status.CLOSED:
        messages.warning(request, 'Kapalı biletler transfer edilemez.')
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
    ticket.transfer(new_department, new_category)
    log_ticket_action(
        ticket, user,
        f'Bilet {old_department.name if old_department else "?"} -> {new_department.name} departmanına transfer edildi.',
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

    if ticket.assigned_to and ticket.assigned_to != user:
        Notification.objects.create(
            recipient=ticket.assigned_to,
            ticket=ticket,
            message=(
                f'Üstlendiğiniz bilet "{ticket.subject}" (#{ticket.pk}) '
                f'{new_department.name} departmanına transfer edildi.'
            ),
        )

    messages.success(
        request,
        f'Bilet #{ticket.pk} "{new_department.name}" departmanına transfer edildi.',
    )

    # Eğer kullanıcı Admin değilse ve bilet sahibi değilse, transfer sonrası bileti göremez
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
        # Sender sadece HENÜZ atanmamış (assigned_to is None) ve OPEN biletini düzenleyebilir
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
        log_ticket_action(self.object, self.request.user, 'Bilet güncellendi.')
        messages.success(self.request, f'{self.object.code} başarıyla güncellendi.')
        return response


# Bilet yorum ekleme — Talep sahibi veya ilgili personel
@login_required
def ticket_add_comment_view(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden('Sadece POST istekleri kabul edilir.')

    ticket = get_object_or_404(Ticket, pk=pk)
    user = request.user

    # Erişim kontrolü: sender, aynı departman personeli/yöneticisi veya admin
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

    # Talep sahibi yorum yazdıysa personele bildir; personel yazdıysa talep sahibine bildir
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


# Bilet yeniden açma — Talep sahibi veya Admin (CLOSED -> OPEN)
@login_required
def ticket_reopen_view(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden('Sadece POST istekleri kabul edilir.')

    ticket = get_object_or_404(Ticket, pk=pk)
    user = request.user

    is_sender = (ticket.sender == user)
    is_admin = (user.role == Role.ADMIN)

    if not (is_sender or is_admin):
        return HttpResponseForbidden('Sadece talep sahibi veya Admin bileti yeniden açabilir.')

    if ticket.status != Status.CLOSED:
        messages.warning(request, 'Sadece kapalı biletler yeniden açılabilir.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    ticket.reopen()
    log_ticket_action(ticket, user, 'Bilet yeniden açıldı.')

    if ticket.department:
        from identity.models import User as UserModel
        agents = UserModel.objects.filter(
            department=ticket.department,
            role__in=[Role.AGENT, Role.MANAGER],
            is_active=True,
        ).exclude(pk=user.pk)
        for agent in agents:
            Notification.objects.create(
                recipient=agent,
                ticket=ticket,
                message=(
                    f'"{ticket.subject}" (#{ticket.pk}) bileti yeniden açıldı.'
                ),
            )

    messages.success(request, f'Bilet #{ticket.pk} yeniden açıldı.')
    return redirect('tickets:ticket_detail', pk=ticket.pk)


# Toplu bilet işlemi — Admin / Manager (kapsamlarına göre)
@login_required
def ticket_bulk_action_view(request):
    if request.method != 'POST':
        return HttpResponseForbidden('Sadece POST istekleri kabul edilir.')

    user = request.user
    if user.role not in (Role.MANAGER, Role.ADMIN):
        return HttpResponseForbidden('Bu işlem için yetkiniz bulunmamaktadır.')

    action = request.POST.get('action', '')
    ticket_ids = request.POST.getlist('ticket_ids')
    if not ticket_ids:
        messages.warning(request, 'Lütfen en az bir bilet seçin.')
        return redirect('tickets:ticket_list')

    qs = Ticket.objects.filter(pk__in=ticket_ids)
    # Manager kapsamı: sadece kendi departmanı
    if user.role == Role.MANAGER:
        qs = qs.filter(department=user.department)

    if action == 'close':
        # Sadece İŞLEMDEKİ veya AÇIK biletler kapatılabilir
        from django.utils import timezone
        target = qs.exclude(status=Status.CLOSED)
        ids = list(target.values_list('pk', flat=True))
        count = target.update(
            status=Status.CLOSED,
            closed_at=timezone.now(),
            resolution_note='Toplu işlem ile kapatıldı.',
        )
        # Audit log
        for tid in ids:
            TicketHistory.objects.create(
                ticket_id=tid, actor=user,
                action='Bilet kapatıldı. Çözüm: Toplu işlem ile kapatıldı.',
            )
        messages.success(request, f'{count} bilet kapatıldı.')

    elif action == 'reopen':
        target = qs.filter(status=Status.CLOSED)
        ids = list(target.values_list('pk', flat=True))
        count = target.update(
            status=Status.OPEN, assigned_to=None, closed_at=None,
        )
        for tid in ids:
            TicketHistory.objects.create(
                ticket_id=tid, actor=user, action='Bilet yeniden açıldı.',
            )
        messages.success(request, f'{count} bilet yeniden açıldı.')

    elif action == 'delete':
        # Silme: Admin her zaman, Manager sadece kendi departmanı
        count = qs.count()
        qs.delete()
        messages.success(request, f'{count} bilet silindi.')

    elif action.startswith('priority:'):
        # priority:HIGH gibi
        new_priority = action.split(':', 1)[1]
        if new_priority not in dict(Priority.choices):
            messages.error(request, 'Geçersiz öncelik.')
            return redirect('tickets:ticket_list')
        count = qs.update(priority=new_priority)
        messages.success(request, f'{count} biletin önceliği "{dict(Priority.choices)[new_priority]}" olarak ayarlandı.')

    else:
        messages.error(request, 'Geçersiz işlem.')

    return redirect('tickets:ticket_list')


# Bilet eki silme — Yükleyen, talep sahibi veya ilgili Manager/Admin
@login_required
def ticket_attachment_delete_view(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden('Sadece POST istekleri kabul edilir.')

    attachment = get_object_or_404(TicketAttachment.objects.select_related('ticket'), pk=pk)
    ticket = attachment.ticket
    user = request.user

    # Yükleyen her zaman silebilir; talep sahibi sadece bilet henüz atanmamışsa
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
def ticket_delete_view(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden('Sadece POST istekleri kabul edilir.')

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


# Etiket CRUD (Sadece Admin)

class TagListView(AdminRequiredMixin, ListView):
    model = Tag
    template_name = 'tickets/tag_list.html'
    context_object_name = 'tags'


class TagCreateView(AdminRequiredMixin, CreateView):
    model = Tag
    template_name = 'tickets/tag_form.html'
    fields = ['name', 'color']
    success_url = reverse_lazy('tickets:tag_list')

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
