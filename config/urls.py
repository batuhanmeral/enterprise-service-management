from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

from config.views import DashboardView

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path('', DashboardView.as_view(), name='home'),
    path('identity/', include('identity.urls')),
    path('departments/', include('departments.urls')),
    path('tickets/', include('tickets.urls')),
    path('notifications/', include('notifications.urls')),
    path('reports/', include('reports.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)