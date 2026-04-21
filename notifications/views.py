from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView
from django.http import HttpResponseForbidden
from django.contrib import messages

from .models import Notification


# Bildirim listeleme - Sadece giriş yapan kullanıcının bildirimleri
class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 30

    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user,
        ).select_related('ticket')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Okunmamış bildirim sayısını bağlama ekle
        context['unread_count'] = Notification.objects.filter(
            recipient=self.request.user,
            is_read=False,
        ).count()
        return context


# Tek bildirimi okundu olarak işaretle
@login_required
def notification_mark_read_view(request, pk):
    notification = get_object_or_404(Notification, pk=pk)

    # Yetki kontrolü: Sadece bildirimin alıcısı işaretleyebilir
    if notification.recipient != request.user:
        return HttpResponseForbidden('Bu bildirime erişim yetkiniz yok.')

    notification.mark_as_read()
    messages.info(request, 'Bildirim okundu olarak işaretlendi.')
    return redirect('notifications:notification_list')


# Tüm bildirimleri toplu okundu olarak işaretle
@login_required
def notification_mark_all_read_view(request):
    if request.method != 'POST':
        return HttpResponseForbidden('Sadece POST istekleri kabul edilir.')

    count = Notification.objects.filter(
        recipient=request.user,
        is_read=False,
    ).update(is_read=True)

    messages.info(request, f'{count} bildirim okundu olarak işaretlendi.')
    return redirect('notifications:notification_list')
