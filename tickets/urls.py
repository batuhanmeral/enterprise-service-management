from django.urls import path
from . import views

app_name = 'tickets'

urlpatterns = [
    # Bilet listeleme (rol bazlı filtrelemeli)
    path('', views.TicketListView.as_view(), name='ticket_list'),

    # Kanban görünümü
    path('kanban/', views.KanbanView.as_view(), name='kanban'),

    # AJAX durum değiştirme (kanban drag-drop)
    path('<int:pk>/change-status/', views.ticket_change_status_view, name='ticket_change_status'),

    # Audit Log (sistem genelinde tüm bilet aksiyonları, ADMIN)
    path('audit-log/', views.AuditLogListView.as_view(), name='audit_log'),

    # Toplu işlem (Manager/Admin)
    path('bulk-action/', views.ticket_bulk_action_view, name='ticket_bulk_action'),

    # Yeni bilet oluşturma
    path('create/', views.TicketCreateView.as_view(), name='ticket_create'),

    # Bilet detayı
    path('<int:pk>/', views.TicketDetailView.as_view(), name='ticket_detail'),

    # Bilet güncelleme
    path('<int:pk>/update/', views.TicketUpdateView.as_view(), name='ticket_update'),

    # Bilet silme
    path('<int:pk>/delete/', views.ticket_delete_view, name='ticket_delete'),

    # Bilet üstlenme (İşlemde)
    path('<int:pk>/take/', views.ticket_take_view, name='ticket_take'),

    # Bilet atama — Admin tüm departmanlara, Manager kendi departmanına
    path('<int:pk>/assign/', views.ticket_assign_view, name='ticket_assign'),

    # Bileti çözüldü olarak işaretle (IN_PROGRESS -> RESOLVED)
    path('<int:pk>/resolve/', views.ticket_resolve_view, name='ticket_resolve'),

    # Bilet transfer
    path('<int:pk>/transfer/', views.ticket_transfer_view, name='ticket_transfer'),

    # Bilet yorum ekleme
    path('<int:pk>/comment/', views.ticket_add_comment_view, name='ticket_add_comment'),

    # Bilet yeniden açma — sadece Admin (CLOSED/ESCALATED -> OPEN)
    path('<int:pk>/reopen/', views.ticket_reopen_view, name='ticket_reopen'),

    # Çözüm onayı — RESOLVED -> CLOSED
    path('<int:pk>/confirm-resolution/', views.ticket_confirm_resolution_view, name='ticket_confirm_resolution'),

    # Çözüm reddi — RESOLVED -> IN_PROGRESS (gerekçeli) veya 3. red ESCALATED
    path('<int:pk>/reject-resolution/', views.ticket_reject_resolution_view, name='ticket_reject_resolution'),

    # CSAT puanı — sadece CLOSED bilete sender 1-5 verir
    path('<int:pk>/rate/', views.ticket_rate_csat_view, name='ticket_rate_csat'),

    # Dosya eki silme
    path('attachments/<int:pk>/delete/', views.ticket_attachment_delete_view, name='ticket_attachment_delete'),

    # Etiket CRUD (Admin)
    path('tags/', views.TagListView.as_view(), name='tag_list'),
    path('tags/create/', views.TagCreateView.as_view(), name='tag_create'),
    path('tags/<int:pk>/update/', views.TagUpdateView.as_view(), name='tag_update'),
    path('tags/<int:pk>/delete/', views.TagDeleteView.as_view(), name='tag_delete'),
]
