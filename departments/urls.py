from django.urls import path
from . import views

app_name = 'departments'

urlpatterns = [
    path('', views.DepartmentListView.as_view(), name='department_list'),
    path('create/', views.DepartmentCreateView.as_view(), name='department_create'),
    # AJAX: Departmana ait kategorileri JSON olarak döndürür
    path('<int:pk>/categories/', views.department_categories_api, name='department_categories_api'),
]