# Her sayfada okunmamış bildirim sayısını template'lere aktaran context processor
def notification_count(request):
    if request.user.is_authenticated:
        from notifications.models import Notification
        count = Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count()
        return {'unread_notification_count': count}
    return {'unread_notification_count': 0}
