import re

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView, FormView, ListView, DetailView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.http import HttpResponseForbidden
from django.contrib import messages
from django import forms

from django.db.models import Case, IntegerField, Max, Q, When

from rest_framework.authtoken.models import Token

from .models import User, Role
from .audit import audit_log, AuditCategory
from departments.models import Department
from notifications.models import Notification
from tickets.models import Ticket, TicketHistory, TicketActionType


def _build_user_resolution_stats(profile_user):
    """Bir personelin çözdüğü biletleri ve kategori başarı oranlarını hesaplar.

    Başarı kuralı: Kullanıcının son kapatma aksiyonu biletin en son kapatmasıysa,
    talep sahibi çözümü onayladıysa ve kapanıştan sonra bilet yeniden açılmadıysa
    "başarılı" sayılır.

    Sorgular `action_type` enum'u üzerinden yapılır — text değişikliklerinden bağımsız.
    """
    # Kullanıcının her bilete yaptığı son kapatma zamanı
    close_events = (
        TicketHistory.objects
        .filter(actor=profile_user, action_type=TicketActionType.CLOSED)
        .values('ticket_id')
        .annotate(latest_close=Max('created_at'))
    )
    close_map = {e['ticket_id']: e['latest_close'] for e in close_events}

    if not close_map:
        return [], []

    ticket_ids = list(close_map.keys())
    # Biletin genelindeki en son kapatma zamanı (aktor bağımsız)
    latest_close_all = (
        TicketHistory.objects
        .filter(ticket_id__in=ticket_ids, action_type=TicketActionType.CLOSED)
        .values('ticket_id')
        .annotate(latest_close=Max('created_at'))
    )
    latest_close_map = {e['ticket_id']: e['latest_close'] for e in latest_close_all}

    tickets = (
        Ticket.objects
        .filter(pk__in=ticket_ids)
        .select_related('category', 'department', 'sender')
    )

    # Bu biletlerdeki tüm reopen olayları (zaman damgası ile)
    # REOPENED veya RESOLUTION_REJECTED — her ikisi de bileti yeniden açar
    reopen_events = (
        TicketHistory.objects
        .filter(
            ticket_id__in=ticket_ids,
            action_type__in=[TicketActionType.REOPENED, TicketActionType.RESOLUTION_REJECTED],
        )
        .values('ticket_id', 'created_at')
    )
    reopen_map = {}
    for r in reopen_events:
        reopen_map.setdefault(r['ticket_id'], []).append(r['created_at'])

    solved_list = []
    for t in tickets:
        latest_close = close_map[t.pk]
        is_latest_closer = latest_close == latest_close_map.get(t.pk)
        was_reopened = any(rt > latest_close for rt in reopen_map.get(t.pk, []))
        is_approved = t.resolution_confirmed is True
        solved_list.append({
            'ticket': t,
            'closed_at': latest_close,
            'is_success': (is_latest_closer and is_approved and not was_reopened),
        })
    solved_list.sort(key=lambda x: x['closed_at'], reverse=True)

    # Kategori bazlı başarı/başarısızlık dağılımı
    cat_buckets = {}
    NO_CATEGORY = '— Kategorisiz —'
    for entry in solved_list:
        cat = entry['ticket'].category
        key = cat.name if cat else NO_CATEGORY
        bucket = cat_buckets.setdefault(key, {'name': key, 'success': 0, 'failure': 0, 'total': 0})
        if entry['is_success']:
            bucket['success'] += 1
        else:
            bucket['failure'] += 1
        bucket['total'] += 1

    cat_stats = list(cat_buckets.values())
    for s in cat_stats:
        s['success_rate'] = round(s['success'] * 100 / s['total'], 1) if s['total'] else 0.0
    cat_stats.sort(key=lambda x: (-x['total'], x['name']))

    return solved_list, cat_stats


# Telefon numarası TR formatı: 11 haneli, "0" ile başlamalı (ör. 05XX XXX XX XX)
PHONE_DIGIT_COUNT = 11

# Kullanıcı giriş formu
class LoginForm(forms.Form):
    username = forms.CharField(
        label='Kullanıcı Adı',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Kullanıcı adınızı girin',
        }),
    )
    password = forms.CharField(
        label='Şifre',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Şifrenizi girin',
        }),
    )

# Kullanıcı giriş görünümü
class LoginView(FormView):
    template_name = 'identity/login.html'
    form_class = LoginForm
    success_url = reverse_lazy('dashboard:home')

    def form_valid(self, form):
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        user = authenticate(self.request, username=username, password=password)

        if user is not None:
            login(self.request, user)
            audit_log(self.request, AuditCategory.AUTH, 'Giriş başarılı', actor=user, target=user)
            messages.success(self.request, f'Hoş geldiniz, {user.get_full_name() or user.username}!')
            next_url = self.request.GET.get('next', self.get_success_url())
            return redirect(next_url)
        else:
            # Pasif hesap kontrolü — daha bilgilendirici mesaj
            try:
                existing = User.objects.get(username=username)
                audit_log(self.request, AuditCategory.AUTH,
                          f'Başarısız giriş denemesi (kullanıcı: {username})',
                          actor=None, target=existing)
                if not existing.is_active:
                    messages.warning(
                        self.request,
                        'Hesabınız henüz admin tarafından onaylanmamıştır. '
                        'Lütfen onay sürecini bekleyin.',
                    )
                    return self.form_invalid(form)
            except User.DoesNotExist:
                audit_log(self.request, AuditCategory.AUTH,
                          f'Başarısız giriş denemesi (bilinmeyen kullanıcı: {username})',
                          actor=None)
            messages.error(self.request, 'Geçersiz kullanıcı adı veya şifre.')
            return self.form_invalid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


# Kullanıcı çıkış işlemi
def logout_view(request):
    actor = request.user if request.user.is_authenticated else None
    if actor:
        audit_log(request, AuditCategory.AUTH, 'Çıkış yapıldı', actor=actor, target=actor)
    logout(request)
    messages.info(request, 'Başarıyla çıkış yapıldı.')
    return redirect('identity:login')


# Kayıt sırasında seçilebilen roller — ADMIN HARİÇ.
# ADMIN sadece mevcut adminlerin oluşturabildiği bir roldür (UserCreateView).
REGISTER_ROLE_CHOICES = [
    (r.value, r.label) for r in Role if r != Role.ADMIN
]


# Kayıt formu — kullanıcı opsiyonel olarak rol ve departman talep edebilir;
# admin onaylarken bu talepleri görür ve gerekirse değiştirebilir.
class RegisterForm(forms.ModelForm):
    password = forms.CharField(
        label='Şifre',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Şifre belirleyin',
        }),
    )
    password_confirm = forms.CharField(
        label='Şifre Tekrar',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Şifrenizi tekrar girin',
        }),
    )
    # Opsiyonel rol talebi — ADMIN listede yok (yetki yükseltme önlenir)
    role = forms.ChoiceField(
        label='Rol',
        required=False,
        choices=[('', '— Seçilmedi —')] + REGISTER_ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    # Opsiyonel departman talebi
    department = forms.ModelChoiceField(
        label='Departman',
        required=False,
        queryset=None,                               # __init__'te doldurulur
        empty_label='— Seçilmedi —',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone',
                  'role', 'department']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.order_by('name')

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Bu kullanıcı adı zaten kullanılıyor.')
        return username

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '') or ''
        phone = phone.strip()
        if not phone:
            return None
        digits = re.sub(r'\D', '', phone)
        if len(digits) != PHONE_DIGIT_COUNT:
            raise forms.ValidationError(
                f'Telefon numarası {PHONE_DIGIT_COUNT} haneli olmalıdır (ör. 05XX XXX XX XX).'
            )
        if not digits.startswith('0'):
            raise forms.ValidationError('Telefon numarası "0" ile başlamalıdır.')
        return digits

    def clean_password(self):
        password = self.cleaned_data.get('password', '')
        if len(password) < 8:
            raise forms.ValidationError('Şifre en az 8 karakter olmalıdır.')
        return password

    def clean_password_confirm(self):
        password = self.cleaned_data.get('password')
        password_confirm = self.cleaned_data.get('password_confirm')
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError('Şifreler eşleşmiyor.')
        return password_confirm

    def clean_role(self):
        # ADMIN seçimi POST manipülasyonu ile bile kabul edilmez (defansif kontrol)
        role = self.cleaned_data.get('role') or ''
        if role == Role.ADMIN:
            raise forms.ValidationError('Admin rolü kayıt sırasında seçilemez.')
        return role

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        # Talep edilen rol/departman korunur ama hesap pasif —
        # ADMIN onaylayana kadar giriş yapılamaz, admin gerekirse değiştirir.
        # Rol seçilmediyse varsayılan EMPLOYEE.
        if not self.cleaned_data.get('role'):
            user.role = Role.EMPLOYEE
        # Defansif: ADMIN değerinin form üzerinden sızmasını önle
        if user.role == Role.ADMIN:
            user.role = Role.EMPLOYEE
        user.is_active = False
        if commit:
            user.save()
        return user

# Kayıt view'ı — anonim kullanıcılar için
class RegisterView(FormView):
    template_name = 'identity/register.html'
    form_class = RegisterForm
    success_url = reverse_lazy('identity:login')

    def form_valid(self, form):
        new_user = form.save()
        # Talep edilen rol/departman audit kaydında ve bildirimde belirtilir
        request_summary = f'rol: {new_user.get_role_display()}'
        if new_user.department:
            request_summary += f', departman: {new_user.department.name}'
        audit_log(self.request, AuditCategory.USER,
                  f'Yeni kullanıcı kaydı (onay bekliyor): {new_user.username} ({request_summary})',
                  actor=None, target=new_user)
        # Tüm aktif ADMIN'lere onay bekleyen kullanıcı bildirimi gönder
        admins = User.objects.filter(role=Role.ADMIN, is_active=True)
        full_name = new_user.get_full_name() or new_user.username
        Notification.objects.bulk_create([
            Notification(
                recipient=admin,
                ticket=None,
                message=(
                    f'Yeni kullanıcı kaydı: "{full_name}" (@{new_user.username}) — '
                    f'{request_summary}. Onayınızı bekliyor.'
                ),
            )
            for admin in admins
        ])
        messages.success(
            self.request,
            'Kayıt başarılı! Hesabınız admin onayına gönderildi. '
            'Onaylandıktan sonra giriş yapabilirsiniz.',
        )
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard:home')
        return super().dispatch(request, *args, **kwargs)


# Kullanıcı profil görünümü
class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'identity/profile.html'


# Kullanıcı bilgilerini güncelleme
@login_required
def profile_update_view(request):
    if request.method != 'POST':
        return redirect('identity:profile')

    user = request.user
    phone_raw = request.POST.get('phone', '').strip()
    phone_value = None
    if phone_raw:
        digits = re.sub(r'\D', '', phone_raw)
        if len(digits) != PHONE_DIGIT_COUNT or not digits.startswith('0'):
            messages.error(
                request,
                f'Telefon numarası {PHONE_DIGIT_COUNT} haneli olmalı ve "0" ile başlamalıdır.',
            )
            return redirect('identity:profile')
        phone_value = digits

    user.first_name = request.POST.get('first_name', '').strip()
    user.last_name = request.POST.get('last_name', '').strip()
    user.email = request.POST.get('email', '').strip()
    user.phone = phone_value
    update_fields = ['first_name', 'last_name', 'email', 'phone']

    if 'avatar' in request.FILES:
        user.avatar = request.FILES['avatar']
        update_fields.append('avatar')

    user.save(update_fields=update_fields)
    audit_log(request, AuditCategory.USER, 'Profil bilgileri güncellendi', target=user)
    messages.success(request, 'Profil bilgileriniz başarıyla güncellendi.')
    return redirect('identity:profile')


# Kullanıcı kendi şifresini değiştirir
@login_required
def password_change_view(request):
    if request.method != 'POST':
        return redirect('identity:profile')

    form = PasswordChangeForm(user=request.user, data=request.POST)
    if form.is_valid():
        user = form.save()
        # Oturumun geçersizleşmemesi için session hash'i güncelle
        update_session_auth_hash(request, user)
        audit_log(request, AuditCategory.AUTH, 'Şifre değiştirildi', target=user)
        messages.success(request, 'Şifreniz başarıyla değiştirildi.')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{error}')

    return redirect('identity:profile')


# Kullanıcı kendi hesabını siler (deaktif eder ve çıkış yapar)
@login_required
@require_POST
def profile_delete_view(request):
    user = request.user
    username = user.username

    # Hesabı deaktif et ve çıkış yap
    user.is_active = False
    user.save(update_fields=['is_active'])
    audit_log(request, AuditCategory.USER, 'Kullanıcı kendi hesabını deaktif etti',
              actor=user, target=user)
    logout(request)

    messages.info(request, f'"{username}" hesabınız başarıyla silindi.')
    return redirect('identity:login')

# Yetki kontrolü mixin — Sadece ADMIN rolü erişebilir
class AdminRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != Role.ADMIN:
            return HttpResponseForbidden('Bu sayfaya erişim yetkiniz bulunmamaktadır.')
        return super().dispatch(request, *args, **kwargs)


# MANAGER veya ADMIN rolündeki kullanıcılar erişebilir
class ManagerOrAdminRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role not in (Role.MANAGER, Role.ADMIN):
            return HttpResponseForbidden('Bu sayfaya erişim yetkiniz bulunmamaktadır.')
        return super().dispatch(request, *args, **kwargs)

# Kullanıcı listesi — Sadece ADMIN
class UserListView(AdminRequiredMixin, ListView):
    model = User
    template_name = 'identity/user_list.html'
    context_object_name = 'users'
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.select_related('department')

        # Serbest arama (?q=ahmet) — username/ad/soyad/email içinde arar
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
            )

        # Rol filtresi (?role=ADMIN)
        role_filter = self.request.GET.get('role')
        if role_filter and role_filter in dict(Role.choices):
            qs = qs.filter(role=role_filter)

        # Departman filtresi (?department=<id>)
        department_filter = self.request.GET.get('department')
        if department_filter and department_filter.isdigit():
            qs = qs.filter(department_id=int(department_filter))
        elif department_filter == 'none':
            qs = qs.filter(department__isnull=True)

        # Durum filtresi (?status=active|inactive)
        status_filter = self.request.GET.get('status')
        if status_filter == 'active':
            qs = qs.filter(is_active=True)
        elif status_filter == 'inactive':
            qs = qs.filter(is_active=False)

        # Sıralama (?sort=username|-username|role|department)
        sort = self.request.GET.get('sort', 'username')
        if sort in ('role', '-role'):
            role_order = Case(
                When(role=Role.ADMIN, then=0),
                When(role=Role.MANAGER, then=1),
                When(role=Role.AGENT, then=2),
                When(role=Role.EMPLOYEE, then=3),
                default=4,
                output_field=IntegerField(),
            )
            qs = qs.annotate(role_order=role_order)
            if sort == 'role':
                return qs.order_by('role_order', 'username')
            return qs.order_by('-role_order', 'username')

        allowed_sorts = {
            'username': 'username',
            '-username': '-username',
            'role': 'role',
            '-role': '-role',
            'department': 'department__name',
            '-department': '-department__name',
            'name': 'first_name',
            '-name': '-first_name',
        }
        qs = qs.order_by(allowed_sorts.get(sort, 'username'))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Onay bekleyen kullanıcı sayısı (filtrelerden bağımsız tüm pasifler)
        context['pending_count'] = User.objects.filter(is_active=False).count()

        # Filtre dropdown verileri
        context['role_choices'] = Role.choices
        context['departments'] = Department.objects.order_by('name')

        # Mevcut filtre değerleri (formda seçili göstermek için)
        context['current_q'] = self.request.GET.get('q', '')
        context['current_role'] = self.request.GET.get('role', '')
        context['current_department'] = self.request.GET.get('department', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['current_sort'] = self.request.GET.get('sort', 'username')
        return context

# Kullanıcı detay — Sadece ADMIN
class UserDetailView(AdminRequiredMixin, DetailView):
    model = User
    template_name = 'identity/user_detail.html'
    context_object_name = 'profile_user'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile_user = self.object
        context['sent_tickets_count'] = profile_user.sent_tickets.count()
        context['activity'] = (
            TicketHistory.objects
            .filter(actor=profile_user)
            .select_related('ticket')
            .order_by('-created_at')[:30]
        )

        # Çözülen biletler + kategori başarı metrikleri (sadece bilet kapatan roller)
        if profile_user.role in (Role.AGENT, Role.MANAGER, Role.ADMIN):
            solved, cat_stats = _build_user_resolution_stats(profile_user)
            context['solved_tickets'] = solved
            context['category_stats'] = cat_stats
            context['solved_success_count'] = sum(1 for s in solved if s['is_success'])
            context['solved_failure_count'] = sum(1 for s in solved if not s['is_success'])
            context['solved_total_count'] = len(solved)
            if context['solved_total_count']:
                context['solved_success_rate'] = round(
                    context['solved_success_count'] * 100 / context['solved_total_count'], 1
                )
            else:
                context['solved_success_rate'] = 0.0
        return context

# Kullanıcı oluşturma formu (Admin tarafından)
class UserCreateForm(forms.ModelForm):
    password = forms.CharField(
        label='Şifre',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Şifre belirleyin',
        }),
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'role', 'department']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user

# Yeni kullanıcı oluşturma — Sadece ADMIN
class UserCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = 'identity/user_form.html'
    success_url = reverse_lazy('identity:user_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        audit_log(self.request, AuditCategory.USER,
                  f'Yeni kullanıcı oluşturuldu: {self.object.username}',
                  target=self.object)
        messages.success(self.request, f'"{self.object.username}" kullanıcısı başarıyla oluşturuldu.')
        return response

# Kullanıcı güncelleme formu (şifresiz)
class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'role', 'department', 'is_active']

# Kullanıcı güncelleme — Sadece ADMIN
class UserUpdateView(AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = 'identity/user_form.html'
    context_object_name = 'profile_user'

    def get_success_url(self):
        return reverse_lazy('identity:user_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        audit_log(self.request, AuditCategory.USER,
                  f'Kullanıcı güncellendi: {self.object.username}',
                  target=self.object)
        messages.success(self.request, f'"{self.object.username}" kullanıcısı başarıyla güncellendi.')
        return response

# Kullanıcı silme — Sadece ADMIN.
# Onaylanmış (aktif) hesaplar kalıcı olarak silinir; ilişkili bilet/yorum/geçmiş
# kayıtları FK'lerdeki SET_NULL davranışı sayesinde sistemde kalır.
# Henüz onaylanmamış (pasif) hesaplar da kalıcı silinir — aksi halde "Onay Bekleyenler"
# listesinde geri görünürlerdi.
@login_required
@require_POST
def user_delete_view(request, pk):
    if request.user.role != Role.ADMIN:
        return HttpResponseForbidden('Bu işlem için yetkiniz bulunmamaktadır.')

    user = get_object_or_404(User, pk=pk)

    # Admin kendini silemez
    if user == request.user:
        messages.warning(request, 'Kendi hesabınızı silemezsiniz.')
        return redirect('identity:user_detail', pk=pk)

    username = user.username
    # API token'larını önce iptal et (varsa)
    Token.objects.filter(user=user).delete()
    user.delete()
    audit_log(request, AuditCategory.USER, f'Kullanıcı kalıcı silindi: {username}',
              target=username)

    messages.success(request, f'"{username}" kullanıcısı kalıcı olarak silindi.')
    return redirect('identity:user_list')

# Kullanıcıyı deaktif et / aktif et — Sadece ADMIN. Silme değil; sadece is_active toggle.
@login_required
@require_POST
def user_deactivate_view(request, pk):
    if request.user.role != Role.ADMIN:
        return HttpResponseForbidden('Bu işlem için yetkiniz bulunmamaktadır.')
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.warning(request, 'Kendi hesabınızı deaktif edemezsiniz.')
        return redirect('identity:user_detail', pk=pk)

    if user.is_active:
        user.is_active = False
        user.save(update_fields=['is_active'])
        # API token'larını da iptal et
        Token.objects.filter(user=user).delete()
        audit_log(request, AuditCategory.USER,
                  f'Kullanıcı deaktif edildi: {user.username}', target=user)
        messages.success(request, f'"{user.username}" hesabı deaktif edildi.')
    else:
        user.is_active = True
        user.save(update_fields=['is_active'])
        audit_log(request, AuditCategory.USER,
                  f'Kullanıcı yeniden aktif edildi: {user.username}', target=user)
        messages.success(request, f'"{user.username}" hesabı yeniden aktif edildi.')
    return redirect('identity:user_detail', pk=pk)


# Toplu kullanıcı işlemi — Sadece ADMIN
@login_required
@require_POST
def user_bulk_action_view(request):
    if request.user.role != Role.ADMIN:
        return HttpResponseForbidden('Bu işlem için yetkiniz bulunmamaktadır.')
    action = request.POST.get('action', '')
    user_ids = request.POST.getlist('user_ids')
    if not user_ids:
        messages.warning(request, 'Lütfen en az bir kullanıcı seçin.')
        return redirect('identity:user_list')

    # Admin kendini hiçbir toplu işleme dahil edemesin
    qs = User.objects.filter(pk__in=user_ids).exclude(pk=request.user.pk)

    if action == 'approve':
        count = qs.filter(is_active=False).update(is_active=True)
        audit_log(request, AuditCategory.USER, f'Toplu onay: {count} kullanıcı aktif edildi')
        messages.success(request, f'{count} kullanıcı onaylandı ve aktif edildi.')
    elif action == 'deactivate':
        count = qs.filter(is_active=True).update(is_active=False)
        # Pasifleştirilen hesapların API token'ını da iptal et
        Token.objects.filter(user__in=qs).delete()
        audit_log(request, AuditCategory.USER, f'Toplu deaktif: {count} kullanıcı pasifleştirildi')
        messages.success(request, f'{count} kullanıcı deaktif edildi.')
    else:
        messages.error(request, 'Geçersiz işlem.')

    return redirect('identity:user_list')


# Kullanıcı onaylama — Sadece ADMIN (pasif hesabı aktif yapar)
@login_required
@require_POST
def user_approve_view(request, pk):
    if request.user.role != Role.ADMIN:
        return HttpResponseForbidden('Bu işlem için yetkiniz bulunmamaktadır.')

    user = get_object_or_404(User, pk=pk)
    user.is_active = True
    user.save(update_fields=['is_active'])
    audit_log(request, AuditCategory.USER,
              f'Kullanıcı onaylandı: {user.username}', target=user)

    messages.success(request, f'"{user.username}" kullanıcısı onaylandı ve aktif edildi.')
    return redirect('identity:user_list')
