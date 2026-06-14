from django.urls import path
from . import views

app_name = 'identity'

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/update/', views.profile_update_view, name='profile_update'),
    path('profile/password/', views.password_change_view, name='password_change'),
    path('profile/delete/', views.profile_delete_view, name='profile_delete'),
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/bulk-action/', views.user_bulk_action_view, name='user_bulk_action'),
    path('users/create/', views.UserCreateView.as_view(), name='user_create'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/update/', views.UserUpdateView.as_view(), name='user_update'),
    path('users/<int:pk>/delete/', views.user_delete_view, name='user_delete'),
    path('users/<int:pk>/deactivate/', views.user_deactivate_view, name='user_deactivate'),
    path('users/<int:pk>/approve/', views.user_approve_view, name='user_approve'),
]
