from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages

from identity.models import User, Role
from identity.views import AdminRequiredMixin, ManagerOrAdminRequiredMixin
from identity.audit import audit_log, AuditCategory

from .models import Department, Category


# Departman formu — manager FK kaldırıldı.
# Yöneticiler artık User.role=MANAGER + User.department üzerinden türetilir.
class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'description']


# Departman listeleme — MANAGER doğrudan kendi departmanına yönlendirilir
class DepartmentListView(LoginRequiredMixin, ListView):
    model = Department
    template_name = 'departments/department_list.html'
    context_object_name = 'departments'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == Role.MANAGER:
            if request.user.department_id:
                return redirect('departments:department_detail', pk=request.user.department_id)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Liste görünümünde personel/çalışan/yönetici sayıları annotate edilir;
        # ad listesi DEĞİL — admin sadece detayda yöneticilerin adlarını görür.
        return (
            Department.objects
            .prefetch_related('categories')
            .annotate(
                manager_count=Count(
                    'personnel',
                    filter=Q(personnel__role=Role.MANAGER, personnel__is_active=True),
                    distinct=True,
                ),
                agent_count=Count(
                    'personnel',
                    filter=Q(personnel__role=Role.AGENT, personnel__is_active=True),
                    distinct=True,
                ),
                employee_count=Count(
                    'personnel',
                    filter=Q(personnel__role=Role.EMPLOYEE, personnel__is_active=True),
                    distinct=True,
                ),
            )
        )


# Departman detay — kategoriler, yöneticiler, üyeler
class DepartmentDetailView(LoginRequiredMixin, DetailView):
    model = Department
    template_name = 'departments/department_detail.html'
    context_object_name = 'department'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = (
            self.object.categories
            .annotate(ticket_count=Count('tickets'))
            .order_by('name')
        )
        # Yöneticiler — sadece ADMIN görüntülenebilir/yönetebilir
        context['managers'] = User.objects.filter(
            department=self.object, role=Role.MANAGER,
        ).order_by('first_name', 'last_name', 'username')
        # Diğer üyeler: AGENT + EMPLOYEE
        context['members'] = User.objects.filter(
            department=self.object,
            role__in=[Role.AGENT, Role.EMPLOYEE],
        ).order_by('role', 'first_name', 'last_name')

        # Rol değiştirme dropdown seçenekleri:
        # - ADMIN: AGENT/EMPLOYEE/MANAGER (3'ü de mümkün)
        # - MANAGER: AGENT/EMPLOYEE/MANAGER (üyeleri yönetici yapabilir ama
        #   mevcut MANAGER'ları düşüremez — view-katmanı zorlar)
        context['role_choices'] = [
            (Role.EMPLOYEE, 'Çalışan'),
            (Role.AGENT, 'Personel'),
            (Role.MANAGER, 'Yönetici'),
        ]
        # Atanabilir personel: AGENT rolünde, departmanı boş, aktif
        context['available_personnel'] = User.objects.filter(
            role=Role.AGENT,
            department__isnull=True,
            is_active=True,
        ).order_by('first_name', 'last_name', 'username')
        return context


# Yeni departman oluşturma — Sadece ADMIN
class DepartmentCreateView(AdminRequiredMixin, CreateView):
    model = Department
    template_name = 'departments/department_form.html'
    form_class = DepartmentForm
    success_url = reverse_lazy('departments:department_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        audit_log(self.request, AuditCategory.DEPARTMENT,
                  f'Departman oluşturuldu: {self.object.name}',
                  target=self.object, department=self.object)
        messages.success(self.request, f'"{self.object.name}" departmanı başarıyla oluşturuldu.')
        return response


# Departman güncelleme — ADMIN veya departmanın MANAGER'ı (sadece ad/açıklama)
class DepartmentUpdateView(ManagerOrAdminRequiredMixin, UpdateView):
    model = Department
    template_name = 'departments/department_form.html'
    form_class = DepartmentForm

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        # Manager sadece kendi departmanını düzenleyebilir
        if hasattr(self, 'object') and request.user.role == Role.MANAGER:
            if request.user.department_id != self.object.pk:
                return HttpResponseForbidden('Bu departmanı düzenleme yetkiniz yok.')
        return response

    def get_success_url(self):
        return reverse_lazy('departments:department_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        audit_log(self.request, AuditCategory.DEPARTMENT,
                  f'Departman güncellendi: {self.object.name}',
                  target=self.object, department=self.object)
        messages.success(self.request, f'"{self.object.name}" departmanı başarıyla güncellendi.')
        return response


# Departman silme — Sadece ADMIN
class DepartmentDeleteView(AdminRequiredMixin, DeleteView):
    model = Department
    template_name = 'departments/department_confirm_delete.html'
    context_object_name = 'department'
    success_url = reverse_lazy('departments:department_list')

    def form_valid(self, form):
        department_name = self.object.name
        response = super().form_valid(form)
        audit_log(self.request, AuditCategory.DEPARTMENT,
                  f'Departman silindi: {department_name}', target=department_name)
        messages.success(self.request, f'"{department_name}" departmanı başarıyla silindi.')
        return response


# Kategori oluşturma — Manager veya Admin (departmana bağlı)
class CategoryCreateView(ManagerOrAdminRequiredMixin, CreateView):
    model = Category
    template_name = 'departments/category_form.html'
    fields = ['name', 'description']

    def form_valid(self, form):
        form.instance.department_id = self.kwargs['dept_pk']
        response = super().form_valid(form)
        audit_log(self.request, AuditCategory.CATEGORY,
                  f'Kategori oluşturuldu: {self.object.name}',
                  target=self.object, department=self.object.department)
        messages.success(self.request, f'"{self.object.name}" kategorisi başarıyla oluşturuldu.')
        return response

    def get_success_url(self):
        return reverse_lazy('departments:department_detail', kwargs={'pk': self.kwargs['dept_pk']})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['department'] = get_object_or_404(Department, pk=self.kwargs['dept_pk'])
        return context


# Kategori güncelleme — Manager veya Admin
class CategoryUpdateView(ManagerOrAdminRequiredMixin, UpdateView):
    model = Category
    template_name = 'departments/category_form.html'
    fields = ['name', 'description']

    def get_success_url(self):
        return reverse_lazy('departments:department_detail', kwargs={'pk': self.object.department_id})

    def form_valid(self, form):
        response = super().form_valid(form)
        audit_log(self.request, AuditCategory.CATEGORY,
                  f'Kategori güncellendi: {self.object.name}',
                  target=self.object, department=self.object.department)
        messages.success(self.request, f'"{self.object.name}" kategorisi başarıyla güncellendi.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['department'] = self.object.department
        return context


# Kategori silme — Manager veya Admin
class CategoryDeleteView(ManagerOrAdminRequiredMixin, DeleteView):
    model = Category
    template_name = 'departments/category_confirm_delete.html'
    context_object_name = 'category'

    def get_success_url(self):
        return reverse_lazy('departments:department_detail', kwargs={'pk': self.object.department_id})

    def form_valid(self, form):
        category_name = self.object.name
        dept = self.object.department
        response = super().form_valid(form)
        audit_log(self.request, AuditCategory.CATEGORY,
                  f'Kategori silindi: {category_name}',
                  target=category_name, department=dept)
        messages.success(self.request, f'"{category_name}" kategorisi başarıyla silindi.')
        return response


# Departmana ait kategorileri JSON olarak döndürür
@login_required
def department_categories_api(request, pk):
    categories = Category.objects.filter(department_id=pk).values('id', 'name')
    return JsonResponse(list(categories), safe=False)


# Departmana personel ekleme — Admin veya departmanın yöneticisi
@login_required
@require_POST
def department_add_personnel(request, pk):
    department = get_object_or_404(Department, pk=pk)

    # Yetki: ADMIN her departmana, MANAGER sadece kendi departmanına ekleyebilir
    is_admin = request.user.role == Role.ADMIN
    is_dept_manager = (
        request.user.role == Role.MANAGER
        and request.user.department_id == department.pk
    )
    if not (is_admin or is_dept_manager):
        return HttpResponseForbidden('Bu departmana personel ekleme yetkiniz yok.')

    user_id = request.POST.get('user_id')
    if not user_id:
        messages.error(request, 'Lütfen bir personel seçin.')
        return redirect('departments:department_detail', pk=pk)

    try:
        user = User.objects.get(
            pk=user_id,
            role=Role.AGENT,
            department__isnull=True,
            is_active=True,
        )
    except User.DoesNotExist:
        messages.error(request, 'Seçilen kullanıcı uygun değil veya zaten bir departmana atanmış.')
        return redirect('departments:department_detail', pk=pk)

    user.department = department
    user.save(update_fields=['department'])
    audit_log(request, AuditCategory.DEPARTMENT,
              f'Personel eklendi: {user.username} → {department.name}',
              target=user, department=department)
    messages.success(
        request,
        f'"{user.get_full_name() or user.username}" "{department.name}" departmanına eklendi.',
    )
    return redirect('departments:department_detail', pk=pk)


# Departman üyesinin rolünü değiştir.
# Yetki kuralları:
#   - ADMIN: tüm yönlerde geçiş (EMPLOYEE ↔ AGENT ↔ MANAGER), ayrıca MANAGER → AGENT/EMPLOYEE düşürme
#   - MANAGER: EMPLOYEE/AGENT'ı MANAGER yapabilir; başka MANAGER'ı DÜŞÜREMEZ (admin işi)
@login_required
@require_POST
def department_change_member_role(request, pk, user_pk):
    department = get_object_or_404(Department, pk=pk)

    is_admin = request.user.role == Role.ADMIN
    is_dept_manager = (
        request.user.role == Role.MANAGER
        and request.user.department_id == department.pk
    )
    if not (is_admin or is_dept_manager):
        return HttpResponseForbidden('Bu departmanda rol değiştirme yetkiniz yok.')

    target_user = get_object_or_404(User, pk=user_pk, department=department)

    # Yönetici kendi rolünü değiştiremez
    if target_user == request.user:
        messages.warning(request, 'Kendi rolünüzü değiştiremezsiniz.')
        return redirect('departments:department_detail', pk=pk)

    new_role = request.POST.get('role', '')
    if new_role not in (Role.EMPLOYEE, Role.AGENT, Role.MANAGER):
        messages.error(request, 'Geçersiz rol.')
        return redirect('departments:department_detail', pk=pk)

    if target_user.role == new_role:
        messages.info(request, f'{target_user.get_full_name() or target_user.username} zaten bu rolde.')
        return redirect('departments:department_detail', pk=pk)

    # MANAGER düşürme yetkisi sadece ADMIN'de
    if target_user.role == Role.MANAGER and not is_admin:
        return HttpResponseForbidden('Yöneticilerin rolünü sadece Admin değiştirebilir.')

    old_role = target_user.get_role_display()
    target_user.role = new_role
    target_user.save(update_fields=['role'])

    new_role_display = dict(Role.choices).get(new_role, new_role)
    audit_log(request, AuditCategory.USER,
              f'Kullanıcı rolü değiştirildi: {target_user.username} ({old_role} → {new_role_display})',
              target=target_user, department=department)
    messages.success(
        request,
        f'"{target_user.get_full_name() or target_user.username}" rolü '
        f'"{new_role_display}" olarak güncellendi.',
    )
    return redirect('departments:department_detail', pk=pk)
