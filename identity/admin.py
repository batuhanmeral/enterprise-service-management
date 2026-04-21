from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


# Kullanıcı modelini admin panelinde yönetmek için sınıf
@admin.register(User)
class UserAdmin(BaseUserAdmin):

    # Admin panelinde kullanıcı listesinde gösterilecek alanlar
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'role',
        'department',
        'is_active',
    )

    # Admin panelinde kullanıcı listesinde satır üzerinde düzenlenebilir alanlar
    list_editable = (
        'role',
        'department',
        'is_active',
    )

    # Admin panelinde kullanıcı listesinde filtreleme seçenekleri
    list_filter = (
        'role',
        'department',
        'is_active',
        'date_joined',
    )

    # Admin panelinde kullanıcı listesinde arama yapılacak alanlar
    search_fields = (
        'username',
        'email',
        'first_name',
        'last_name',
        'phone',
    )

    # Varsayılan fieldsets'e rol, departman ve telefon alanlarını ekle
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Kurumsal Bilgiler', {
            'fields': ('role', 'department', 'phone'),
        }),
    )

    # Yeni kullanıcı oluşturma formuna da özel alanları ekle
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Kurumsal Bilgiler', {
            'fields': ('role', 'department', 'phone'),
        }),
    )

    # Admin panelinde kullanıcı listesinde varsayılan sıralama
    ordering = ('username',)

    # Admin panelinde sayfa başına gösterilecek kullanıcı sayısı
    list_per_page = 25

    # Toplu aksiyonlar
    actions = ['make_active', 'make_inactive', 'set_role_employee', 'set_role_agent']

    # Seçili kullanıcıları aktif yap
    @admin.action(description='Seçili kullanıcıları aktif yap')
    def make_active(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} kullanıcı aktif yapıldı.')

    # Seçili kullanıcıları pasif yap
    @admin.action(description='Seçili kullanıcıları pasif yap')
    def make_inactive(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} kullanıcı pasif yapıldı.')

    # Seçili kullanıcıları Çalışan rolüne ata
    @admin.action(description='Seçili kullanıcıların rolünü "Çalışan" yap')
    def set_role_employee(self, request, queryset):
        from .models import Role
        count = queryset.update(role=Role.EMPLOYEE)
        self.message_user(request, f'{count} kullanıcının rolü "Çalışan" olarak güncellendi.')

    # Seçili kullanıcıları Personel rolüne ata
    @admin.action(description='Seçili kullanıcıların rolünü "Personel" yap')
    def set_role_agent(self, request, queryset):
        from .models import Role
        count = queryset.update(role=Role.AGENT)
        self.message_user(request, f'{count} kullanıcının rolü "Personel" olarak güncellendi.')
