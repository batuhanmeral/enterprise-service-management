from django.urls import path
from . import views

app_name = 'tickets'

urlpatterns = [
    # Bilet listeleme (rol bazlı filtrelemeli)
    path('', views.TicketListView.as_view(), name='ticket_list'),

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

    # Bilet kapatma
    path('<int:pk>/close/', views.ticket_close_view, name='ticket_close'),

    # Bilet transfer
    path('<int:pk>/transfer/', views.ticket_transfer_view, name='ticket_transfer'),

    # Bilet yorum ekleme
    path('<int:pk>/comment/', views.ticket_add_comment_view, name='ticket_add_comment'),

    # Bilet yeniden açma (CLOSED -> OPEN)
    path('<int:pk>/reopen/', views.ticket_reopen_view, name='ticket_reopen'),

    # Dosya eki silme
    path('attachments/<int:pk>/delete/', views.ticket_attachment_delete_view, name='ticket_attachment_delete'),

    # Etiket CRUD (Admin)
    path('tags/', views.TagListView.as_view(), name='tag_list'),
    path('tags/create/', views.TagCreateView.as_view(), name='tag_create'),
    path('tags/<int:pk>/update/', views.TagUpdateView.as_view(), name='tag_update'),
    path('tags/<int:pk>/delete/', views.TagDeleteView.as_view(), name='tag_delete'),
]
