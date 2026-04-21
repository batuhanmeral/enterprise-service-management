from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, CreateView, DetailView
from django.urls import reverse_lazy
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.db.models import Q

from .models import Ticket, Status
from notifications.models import Notification
from identity.models import Role


# Bilet listeleme - Rol bazlı filtreleme uygulanır
class TicketListView(LoginRequiredMixin, ListView):
    model = Ticket
    template_name = 'tickets/ticket_list.html'
    context_object_name = 'tickets'
    paginate_by = 20

    def get_queryset(self):
        user = self.request.user
        qs = Ticket.objects.select_related(
            'sender', 'assigned_to', 'department', 'category',
        )

        # Admin: Tüm biletleri görür
        if user.role == Role.ADMIN:
            return qs

        # Personel/Yönetici: Kendi departmanının biletlerini görür
        elif user.role in (Role.AGENT, Role.MANAGER):
            return qs.filter(department=user.department)

        # Kullanıcı: Sadece kendi açtığı biletleri görür
        else:
            return qs.filter(sender=user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_role'] = self.request.user.role
        return context


# Yeni bilet oluşturma - sender otomatik atanır
class TicketCreateView(LoginRequiredMixin, CreateView):
    model = Ticket
    template_name = 'tickets/ticket_form.html'
    fields = ['subject', 'message', 'department', 'category', 'attachment']
    success_url = reverse_lazy('tickets:ticket_list')

    def form_valid(self, form):
        # Sender'ı giriş yapan kullanıcıya ata
        form.instance.sender = self.request.user
        form.instance.status = Status.OPEN
        response = super().form_valid(form)

        messages.success(
            self.request,
            f'Talebiniz başarıyla oluşturuldu. (Bilet #{self.object.pk})',
        )
        return response


# Bilet detay - Rol bazlı erişim kontrolü
class TicketDetailView(LoginRequiredMixin, DetailView):
    model = Ticket
    template_name = 'tickets/ticket_detail.html'
    context_object_name = 'ticket'

    def get_queryset(self):
        user = self.request.user
        qs = Ticket.objects.select_related(
            'sender', 'assigned_to', 'department', 'category',
        )

        # Admin: Tüm biletleri görebilir
        if user.role == Role.ADMIN:
            return qs

        # Personel/Yönetici: Departman biletleri veya kendi açtıkları
        elif user.role in (Role.AGENT, Role.MANAGER):
            return qs.filter(
                Q(department=user.department) | Q(sender=user)
            )

        # Kullanıcı: Sadece kendi biletleri
        else:
            return qs.filter(sender=user)


# Talep üstlenme - Personel bileti üzerine alır (OPEN → IN_PROGRESS)
@login_required
def ticket_take_view(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden('Sadece POST istekleri kabul edilir.')

    user = request.user

    # Yetki kontrolü: Sadece personel/yönetici üstlenebilir
    if user.role not in (Role.AGENT, Role.MANAGER):
        return HttpResponseForbidden('Bu işlem için yetkiniz bulunmamaktadır.')

    ticket = get_object_or_404(Ticket, pk=pk)

    # Departman kontrolü
    if ticket.department != user.department:
        return HttpResponseForbidden('Bu bilet sizin departmanınıza ait değildir.')

    # Durum kontrolü: Sadece OPEN biletler üstlenilebilir
    if ticket.status != Status.OPEN:
        messages.warning(request, 'Bu bilet zaten işlemde veya kapalı durumda.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    # Bileti üstlen
    ticket.take_into_process(personnel=user)

    # Talep sahibine bildirim gönder
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


# Talep kapatma - Atanan personel bileti kapatır (IN_PROGRESS → CLOSED)
@login_required
def ticket_close_view(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden('Sadece POST istekleri kabul edilir.')

    user = request.user
    ticket = get_object_or_404(Ticket, pk=pk)

    # Yetki kontrolü: Sadece atanan personel veya Admin kapatabilir
    is_assigned = (ticket.assigned_to == user)
    is_admin = (user.role == Role.ADMIN)

    if not (is_assigned or is_admin):
        return HttpResponseForbidden(
            'Sadece bileti üstlenen personel veya Admin kapatabilir.'
        )

    # Durum kontrolü: Sadece IN_PROGRESS biletler kapatılabilir
    if ticket.status != Status.IN_PROGRESS:
        messages.warning(request, 'Sadece "İşlemde" durumundaki biletler kapatılabilir.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    # Bileti kapat
    resolution_note = request.POST.get('resolution_note', '')
    ticket.close(resolution_note=resolution_note)

    # Talep sahibine bildirim gönder
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


# Bilet transfer — Başka departmana aktarma (AGENT/MANAGER/ADMIN)
@login_required
def ticket_transfer_view(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    user = request.user

    # Yetki kontrolü: Sadece personel, yönetici veya admin transfer edebilir
    if user.role not in (Role.AGENT, Role.MANAGER, Role.ADMIN):
        return HttpResponseForbidden('Bu işlem için yetkiniz bulunmamaktadır.')

    # Personel/Yönetici kendi departman biletlerini transfer edebilir
    if user.role in (Role.AGENT, Role.MANAGER):
        if ticket.department != user.department:
            return HttpResponseForbidden('Bu bilet sizin departmanınıza ait değildir.')

    # Kapalı biletler transfer edilemez
    if ticket.status == Status.CLOSED:
        messages.warning(request, 'Kapalı biletler transfer edilemez.')
        return redirect('tickets:ticket_detail', pk=ticket.pk)

    if request.method == 'GET':
        # Transfer formu için departman listesi
        from departments.models import Department
        departments = Department.objects.exclude(pk=ticket.department_id)
        return render(request, 'tickets/ticket_transfer.html', {
            'ticket': ticket,
            'departments': departments,
        })

    # POST: Transfer işlemi
    from departments.models import Department, Category
    new_dept_id = request.POST.get('department')
    new_cat_id = request.POST.get('category') or None

    new_department = get_object_or_404(Department, pk=new_dept_id)
    new_category = None
    if new_cat_id:
        new_category = get_object_or_404(Category, pk=new_cat_id, department=new_department)

    old_department = ticket.department

    # Transfer işlemini uygula
    ticket.transfer(new_department, new_category)

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

    # Eski departmandaki atanan personele bildirim
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
    return redirect('tickets:ticket_detail', pk=ticket.pk)

