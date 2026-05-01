from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from drf_spectacular.views import (
    SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView,
)

from identity.api_urls import auth_urlpatterns, user_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),

    # i18n: dil değiştirme (set_language POST endpoint'i)
    path('i18n/', include('django.conf.urls.i18n')),

    # Mevcut SSR URL'ler
    path('', include('dashboard.urls')),
    path('identity/', include('identity.urls')),
    path('departments/', include('departments.urls')),
    path('tickets/', include('tickets.urls')),
    path('notifications/', include('notifications.urls')),
    path('reports/', include('reports.urls')),

    # REST API v1
    path('api/v1/auth/', include((auth_urlpatterns, 'api_auth'))),
    path('api/v1/users/', include((user_urlpatterns, 'api_users'))),
    path('api/v1/departments/', include(('departments.api_urls', 'api_departments'))),
    path('api/v1/tickets/', include(('tickets.api_urls', 'api_tickets'))),
    path('api/v1/notifications/', include(('notifications.api_urls', 'api_notifications'))),
    path('api/v1/reports/', include(('reports.api_urls', 'api_reports'))),
    path('api/v1/dashboard/', include(('dashboard.api_urls', 'api_dashboard'))),

    # OpenAPI / Swagger / ReDoc dokümantasyonu (drf-spectacular)
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Geliştirme ortamında media dosyalarını sun
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)