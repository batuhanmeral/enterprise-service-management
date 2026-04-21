from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.contrib import messages

from .models import Department, Category


# Departman listeleme
class DepartmentListView(LoginRequiredMixin, ListView):
    model = Department
    template_name = 'departments/department_list.html'
    context_object_name = 'departments'


# Yeni departman oluşturma
class DepartmentCreateView(LoginRequiredMixin, CreateView):
    model = Department
    template_name = 'departments/department_form.html'
    fields = ['name', 'description']
    success_url = reverse_lazy('departments:department_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'"{self.object.name}" departmanı başarıyla oluşturuldu.')
        return response


# AJAX endpoint — departmana ait kategorileri JSON olarak döndürür
@login_required
def department_categories_api(request, pk):
    categories = Category.objects.filter(department_id=pk).values('id', 'name')
    return JsonResponse(list(categories), safe=False)
