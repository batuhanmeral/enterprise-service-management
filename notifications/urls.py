from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.NotificationListView.as_view(), name='notification_list'),

    path('<int:pk>/', views.NotificationDetailView.as_view(), name='notification_detail'),

    path('<int:pk>/read/', views.notification_mark_read_view, name='notification_mark_read'),

    path('<int:pk>/delete/', views.notification_delete_view, name='notification_delete'),

    path('mark-all-read/', views.notification_mark_all_read_view, name='notification_mark_all_read'),
]
