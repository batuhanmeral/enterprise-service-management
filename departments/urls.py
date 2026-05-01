from django.urls import path
from . import views

app_name = 'departments'

urlpatterns = [
    path('', views.DepartmentListView.as_view(), name='department_list'),
    path('create/', views.DepartmentCreateView.as_view(), name='department_create'),
    # Departman detay, güncelleme ve silme
    path('<int:pk>/', views.DepartmentDetailView.as_view(), name='department_detail'),
    path('<int:pk>/update/', views.DepartmentUpdateView.as_view(), name='department_update'),
    path('<int:pk>/delete/', views.DepartmentDeleteView.as_view(), name='department_delete'),
    # AJAX: Departmana ait kategorileri JSON olarak döndürür
    path('<int:pk>/categories/', views.department_categories_api, name='department_categories_api'),
    # Personel ekleme (boştaki AGENT kullanıcıları)
    path('<int:pk>/personnel/add/', views.department_add_personnel, name='department_add_personnel'),
    # Üye rolü değiştirme (AGENT ↔ EMPLOYEE)
    path('<int:pk>/members/<int:user_pk>/role/', views.department_change_member_role, name='department_change_member_role'),
    # Kategori CRUD (departman bağlamında)
    path('<int:dept_pk>/categories/create/', views.CategoryCreateView.as_view(), name='category_create'),
    path('categories/<int:pk>/update/', views.CategoryUpdateView.as_view(), name='category_update'),
    path('categories/<int:pk>/delete/', views.CategoryDeleteView.as_view(), name='category_delete'),
]
