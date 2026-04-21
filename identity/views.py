from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.generic import TemplateView, FormView
from django.urls import reverse_lazy
from django.contrib import messages
from django import forms


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
    success_url = reverse_lazy('tickets:ticket_list')

    def form_valid(self, form):
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        user = authenticate(self.request, username=username, password=password)

        if user is not None:
            login(self.request, user)
            messages.success(self.request, f'Hoş geldiniz, {user.get_full_name() or user.username}!')
            # next parametresi varsa oraya yönlendir
            next_url = self.request.GET.get('next', self.get_success_url())
            return redirect(next_url)
        else:
            messages.error(self.request, 'Geçersiz kullanıcı adı veya şifre.')
            return self.form_invalid(form)

    def dispatch(self, request, *args, **kwargs):
        # Zaten giriş yapmış kullanıcıları bilet listesine yönlendir
        if request.user.is_authenticated:
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


# Kullanıcı çıkış işlemi
def logout_view(request):
    logout(request)
    messages.info(request, 'Başarıyla çıkış yapıldı.')
    return redirect('identity:login')


# Kullanıcı profil görünümü
class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'identity/profile.html'


# Kullanıcı bilgilerini güncelleme
@login_required
def profile_update_view(request):
    if request.method != 'POST':
        return redirect('identity:profile')

    user = request.user
    user.first_name = request.POST.get('first_name', '').strip()
    user.last_name = request.POST.get('last_name', '').strip()
    user.email = request.POST.get('email', '').strip()
    user.phone = request.POST.get('phone', '').strip() or None
    user.save(update_fields=['first_name', 'last_name', 'email', 'phone'])

    messages.success(request, 'Profil bilgileriniz başarıyla güncellendi.')
    return redirect('identity:profile')
