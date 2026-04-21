from django.urls import path
from . import views

app_name = 'tickets'

urlpatterns = [
    # Bilet listeleme (rol bazlı filtrelemeli)
    path('', views.TicketListView.as_view(), name='ticket_list'),

    # Yeni bilet oluşturma
    path('create/', views.TicketCreateView.as_view(), name='ticket_create'),

    # Bilet detayı
    path('<int:pk>/', views.TicketDetailView.as_view(), name='ticket_detail'),

    # Bilet üstlenme (İşlemde)
    path('<int:pk>/take/', views.ticket_take_view, name='ticket_take'),

    # Bilet kapatma
    path('<int:pk>/close/', views.ticket_close_view, name='ticket_close'),

    # Bilet transfer
    path('<int:pk>/transfer/', views.ticket_transfer_view, name='ticket_transfer'),
]