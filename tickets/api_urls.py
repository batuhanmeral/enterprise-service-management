from django.urls import path

from . import api_views

urlpatterns = [
    # Bilet listeleme ve oluşturma
    path('', api_views.TicketListCreateAPIView.as_view(), name='api_ticket_list'),
    # Bilet detay, güncelleme ve silme
    path('<int:pk>/', api_views.TicketDetailAPIView.as_view(), name='api_ticket_detail'),
    # Bilet üstlenme (OPEN → IN_PROGRESS)
    path('<int:pk>/take/', api_views.TicketTakeAPIView.as_view(), name='api_ticket_take'),
    # Bileti çözüldü olarak işaretleme (IN_PROGRESS → RESOLVED, sender onayı bekleniyor)
    path('<int:pk>/resolve/', api_views.TicketResolveAPIView.as_view(), name='api_ticket_resolve'),
    # Çözüm onayı (RESOLVED → CLOSED)
    path('<int:pk>/confirm-resolution/', api_views.TicketConfirmResolutionAPIView.as_view(), name='api_ticket_confirm_resolution'),
    # Çözüm reddi (RESOLVED → IN_PROGRESS / ESCALATED, gerekçeli)
    path('<int:pk>/reject-resolution/', api_views.TicketRejectResolutionAPIView.as_view(), name='api_ticket_reject_resolution'),
    # CSAT puanı (CLOSED bilete sender 1-5)
    path('<int:pk>/rate/', api_views.TicketCsatAPIView.as_view(), name='api_ticket_rate'),
    # Bilet transfer (departmanlar arası)
    path('<int:pk>/transfer/', api_views.TicketTransferAPIView.as_view(), name='api_ticket_transfer'),
    # Bilet yeniden açma — Admin override (CLOSED/ESCALATED → OPEN)
    path('<int:pk>/reopen/', api_views.TicketReopenAPIView.as_view(), name='api_ticket_reopen'),
    # Bilet yorumları
    path('<int:pk>/comments/', api_views.TicketCommentListCreateAPIView.as_view(), name='api_ticket_comments'),
]
