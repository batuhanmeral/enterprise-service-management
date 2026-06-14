from django.urls import path
from . import views

app_name = 'tickets'

urlpatterns = [
    path('', views.TicketListView.as_view(), name='ticket_list'),

    path('kanban/', views.KanbanView.as_view(), name='kanban'),

    path('<int:pk>/change-status/', views.ticket_change_status_view, name='ticket_change_status'),

    path('audit-log/', views.AuditLogListView.as_view(), name='audit_log'),

    path('bulk-action/', views.ticket_bulk_action_view, name='ticket_bulk_action'),

    path('create/', views.TicketCreateView.as_view(), name='ticket_create'),

    path('<int:pk>/', views.TicketDetailView.as_view(), name='ticket_detail'),

    path('<int:pk>/update/', views.TicketUpdateView.as_view(), name='ticket_update'),

    path('<int:pk>/delete/', views.ticket_delete_view, name='ticket_delete'),

    path('<int:pk>/take/', views.ticket_take_view, name='ticket_take'),

    path('<int:pk>/assign/', views.ticket_assign_view, name='ticket_assign'),

    path('<int:pk>/resolve/', views.ticket_resolve_view, name='ticket_resolve'),

    path('<int:pk>/transfer/', views.ticket_transfer_view, name='ticket_transfer'),

    path('<int:pk>/comment/', views.ticket_add_comment_view, name='ticket_add_comment'),

    path('<int:pk>/reopen/', views.ticket_reopen_view, name='ticket_reopen'),

    path('<int:pk>/confirm-resolution/', views.ticket_confirm_resolution_view, name='ticket_confirm_resolution'),

    path('<int:pk>/reject-resolution/', views.ticket_reject_resolution_view, name='ticket_reject_resolution'),

    path('<int:pk>/rate/', views.ticket_rate_csat_view, name='ticket_rate_csat'),

    path('attachments/<int:pk>/delete/', views.ticket_attachment_delete_view, name='ticket_attachment_delete'),

    path('tags/', views.TagListView.as_view(), name='tag_list'),
    path('tags/create/', views.TagCreateView.as_view(), name='tag_create'),
    path('tags/<int:pk>/update/', views.TagUpdateView.as_view(), name='tag_update'),
    path('tags/<int:pk>/delete/', views.TagDeleteView.as_view(), name='tag_delete'),
]
