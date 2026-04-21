from django.contrib.auth.models import AbstractUser
from django.db import models


# Kullanıcı rollerini tanımlayan enumeration sınıfı
class Role(models.TextChoices):
    EMPLOYEE = 'EMPLOYEE', 'Çalışan'
    AGENT = 'AGENT', 'Personel'
    MANAGER = 'MANAGER', 'Yönetici'
    ADMIN = 'ADMIN', 'Admin'


# Django AbstractUser genişletilmiş kullanıcı modeli
class User(AbstractUser):

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

    # Model objesinin sistemde metin olarak nasıl temsil edileceğini belirleyen fonksiyon
    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

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
