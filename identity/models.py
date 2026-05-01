from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from .validators import (
    validate_avatar_extension,
    validate_avatar_size,
    validate_avatar_content,
)


# Kullanıcı rollerini tanımlayan enumeration sınıfı
class Role(models.TextChoices):
    EMPLOYEE = 'EMPLOYEE', 'Çalışan'
    AGENT = 'AGENT', 'Personel'
    MANAGER = 'MANAGER', 'Yönetici'
    ADMIN = 'ADMIN', 'Admin'


# Django AbstractUser genişletilmiş kullanıcı modeli
class User(AbstractUser):

    # Kullanıcının profil fotoğrafı (max 2 MB, JPG/PNG/WEBP)
    avatar = models.ImageField(
        upload_to='avatars/',
        blank=True,
        null=True,
        verbose_name='Profil Fotoğrafı',
        validators=[
            validate_avatar_extension,
            validate_avatar_size,
            validate_avatar_content,
        ],
    )

    # Kullanıcının telefon numarası
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Telefon Numarası',
    )

    # Kullanıcının rolü(yetki seviyesi)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.EMPLOYEE,
        verbose_name='Rol',
    )

    # Kullanıcının bağlı olduğu departman
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.SET_NULL, # Departman silinse bile kullanıcı sistemde kalır
        null=True,
        blank=True,
        related_name='personnel',
        verbose_name='Departman',
    )

    # Modelin admin paneli ve veritabanı davranışlarını belirleyen meta-veri sınıfı
    class Meta:
        verbose_name = 'Kullanıcı'
        verbose_name_plural = 'Kullanıcılar'
        ordering = ['username']
        indexes = [
            models.Index(fields=['role', 'department', 'is_active'], name='user_role_dept_active_idx'),
        ]

    # Model objesinin sistemde metin olarak nasıl temsil edileceğini belirleyen fonksiyon
    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    # ADMIN rolü Django admin paneline (is_staff) erişim ima eder; senkronize tut.
    def save(self, *args, **kwargs):
        if self.role == Role.ADMIN and not self.is_staff:
            self.is_staff = True
        super().save(*args, **kwargs)

    # Kullanıcı rolünü kontrol eden yardımcı property'ler
    @property
    def is_employee(self):
        return self.role == Role.EMPLOYEE

    @property
    def is_agent(self):
        return self.role == Role.AGENT

    @property
    def is_manager(self):
        return self.role == Role.MANAGER

    @property
    def is_admin(self):
        return self.role == Role.ADMIN


# Sistem genelinde tüm aksiyonları kaydeden audit log modeli.
# Bilet/Kullanıcı/Departman/Kimlik doğrulama gibi farklı kategorilerdeki olayları tutar.
class AuditLog(models.Model):

    class Category(models.TextChoices):
        TICKET = 'TICKET', 'Bilet'
        USER = 'USER', 'Kullanıcı'
        DEPARTMENT = 'DEPARTMENT', 'Departman'
        CATEGORY = 'CATEGORY', 'Kategori'
        AUTH = 'AUTH', 'Kimlik Doğrulama'
        OTHER = 'OTHER', 'Diğer'

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_actions',
        verbose_name='İşlemi Yapan',
    )
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
        verbose_name='Kategori',
    )
    action = models.CharField(max_length=300, verbose_name='Aksiyon')
    target_repr = models.CharField(max_length=200, blank=True, default='', verbose_name='Hedef')
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name='İlgili Departman',
    )
    ticket = models.ForeignKey(
        'tickets.Ticket',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name='İlgili Bilet',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Tarih')

    class Meta:
        verbose_name = 'Geçmiş Kaydı'
        verbose_name_plural = 'Geçmiş Kayıtları'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['category', '-created_at']),
            models.Index(fields=['actor', '-created_at']),
        ]

    def __str__(self):
        actor_name = self.actor.username if self.actor else 'Sistem'
        return f'[{self.get_category_display()}] {actor_name}: {self.action[:60]}'
