from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    # Bildirim listeleme
    path('', views.NotificationListView.as_view(), name='notification_list'),

    # Tek bildirimi okundu olarak işaretle
    path('<int:pk>/read/', views.notification_mark_read_view, name='notification_mark_read'),

    # Tüm bildirimleri okundu olarak işaretle
    path('mark-all-read/', views.notification_mark_all_read_view, name='notification_mark_all_read'),
]