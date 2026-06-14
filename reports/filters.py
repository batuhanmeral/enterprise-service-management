from urllib.parse import urlencode

from django import forms

from departments.models import Department, Category
from identity.models import User, Role
from tickets.models import Status, Priority, Tag


GRANULARITY_CHOICES = [
    ('day', 'Günlük'),
    ('week', 'Haftalık'),
    ('month', 'Aylık'),
]


class ReportFilterForm(forms.Form):

    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    department = forms.ModelChoiceField(queryset=Department.objects.none(), required=False)
    sender = forms.ModelChoiceField(queryset=User.objects.none(), required=False)
    assigned_to = forms.ModelChoiceField(queryset=User.objects.none(), required=False)
    category = forms.ModelChoiceField(queryset=Category.objects.none(), required=False)
    tag = forms.ModelChoiceField(queryset=Tag.objects.none(), required=False)
    priority = forms.ChoiceField(choices=[('', 'Tümü')] + list(Priority.choices), required=False)
    status = forms.ChoiceField(choices=[('', 'Tümü')] + list(Status.choices), required=False)
    granularity = forms.ChoiceField(choices=GRANULARITY_CHOICES, required=False, initial='month')

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        if user is None or user.role == Role.ADMIN:
            self.fields['department'].queryset = Department.objects.order_by('name')
            self.fields['category'].queryset = (
                Category.objects.select_related('department').order_by('department__name', 'name')
            )
            self.fields['sender'].queryset = (
                User.objects.filter(is_active=True)
                .select_related('department')
                .order_by('department__name', 'first_name', 'last_name')
            )
            self.fields['assigned_to'].queryset = (
                User.objects.filter(is_active=True, role=Role.AGENT)
                .select_related('department')
                .order_by('department__name', 'first_name', 'last_name')
            )
        else:
            self.fields['department'].queryset = Department.objects.filter(pk=user.department_id)
            self.fields['department'].initial = user.department_id
            self.fields['department'].disabled = True
            self.fields['category'].queryset = Category.objects.filter(
                department=user.department
            ).order_by('name')
            base_users = User.objects.filter(
                is_active=True, department=user.department
            ).order_by('first_name', 'last_name')
            self.fields['sender'].queryset = base_users
            self.fields['assigned_to'].queryset = base_users.filter(role=Role.AGENT)

        self.fields['tag'].queryset = Tag.objects.order_by('name')

    def safe_cleaned(self):
        if not self.is_bound:
            return {}
        if self.is_valid():
            return {k: v for k, v in self.cleaned_data.items() if v not in (None, '')}
        return {}

    def apply(self, qs, user):
        if user.role == Role.MANAGER:
            qs = qs.filter(department=user.department)
        elif user.role != Role.ADMIN:
            qs = qs.none()

        data = self.safe_cleaned()
        if data.get('date_from'):
            qs = qs.filter(created_at__date__gte=data['date_from'])
        if data.get('date_to'):
            qs = qs.filter(created_at__date__lte=data['date_to'])
        if data.get('department'):
            qs = qs.filter(department=data['department'])
        if data.get('sender'):
            qs = qs.filter(sender=data['sender'])
        if data.get('assigned_to'):
            qs = qs.filter(assigned_to=data['assigned_to'])
        if data.get('category'):
            qs = qs.filter(category=data['category'])
        if data.get('tag'):
            qs = qs.filter(tags=data['tag'])
        if data.get('priority'):
            qs = qs.filter(priority=data['priority'])
        if data.get('status'):
            qs = qs.filter(status=data['status'])
        return qs.distinct() if data.get('tag') else qs

    def get_granularity(self):
        data = self.safe_cleaned()
        return data.get('granularity') or 'month'

    def as_ticket_query(self, **overrides):
        data = self.safe_cleaned()
        params = {}
        if data.get('date_from'):
            params['date_from'] = data['date_from'].isoformat()
        if data.get('date_to'):
            params['date_to'] = data['date_to'].isoformat()
        if data.get('department'):
            params['department'] = data['department'].pk
        if data.get('sender'):
            params['sender'] = data['sender'].pk
        if data.get('assigned_to'):
            params['assigned_to'] = data['assigned_to'].pk
        if data.get('category'):
            params['category'] = data['category'].pk
        if data.get('tag'):
            params['tag'] = data['tag'].pk
        if data.get('priority'):
            params['priority'] = data['priority']
        if data.get('status'):
            params['status'] = data['status']
        for k, v in overrides.items():
            if v in (None, ''):
                params.pop(k, None)
            else:
                params[k] = v
        return urlencode(params)
