from django.contrib import admin
from django.urls import path, include
from dashboard.views import DashboardView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Ana sayfa — Rol bazlı dashboard
    path('', DashboardView.as_view(), name='dashboard'),
    path('identity/', include('identity.urls')),
    path('departments/', include('departments.urls')),
    path('tickets/', include('tickets.urls')),
    path('notifications/', include('notifications.urls')),
    path('reports/', include('reports.urls')),
]