from django.urls import path

from rest_framework_simplejwt.views import (
    TokenRefreshView, TokenVerifyView,
)

from . import api_views

# Auth endpoint'leri: api/v1/auth/
auth_urlpatterns = [
    path('login/', api_views.LoginAPIView.as_view(), name='api_login'),
    path('logout/', api_views.LogoutAPIView.as_view(), name='api_logout'),
    path('register/', api_views.RegisterAPIView.as_view(), name='api_register'),
    path('profile/', api_views.ProfileAPIView.as_view(), name='api_profile'),
    path('profile/delete/', api_views.ProfileDeleteAPIView.as_view(), name='api_profile_delete'),
    # JWT — refresh token ile yeni access üret; verify ile geçerlilik kontrolü
    path('token/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='api_token_verify'),
]

# User yönetim endpoint'leri: api/v1/users/
user_urlpatterns = [
    path('', api_views.UserListAPIView.as_view(), name='api_user_list'),
    path('create/', api_views.UserCreateAPIView.as_view(), name='api_user_create'),
    path('<int:pk>/', api_views.UserDetailAPIView.as_view(), name='api_user_detail'),
    path('<int:pk>/update/', api_views.UserUpdateAPIView.as_view(), name='api_user_update'),
    path('<int:pk>/delete/', api_views.UserDeleteAPIView.as_view(), name='api_user_delete'),
    path('<int:pk>/approve/', api_views.UserApproveAPIView.as_view(), name='api_user_approve'),
]
