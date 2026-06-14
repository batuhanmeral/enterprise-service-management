from django.db import models


class Department(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Departman Adı',
    )

    description = models.TextField(
        max_length=1000,
        blank=True,
        default='',
        verbose_name='Açıklama',
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Oluşturulma Tarihi',
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Güncellenme Tarihi',
    )

    auto_assign_enabled = models.BooleanField(
        default=True,
        verbose_name='Otomatik Atama',
    )

    last_auto_assigned = models.ForeignKey(
        'identity.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='Son Otomatik Atanan',
    )

    class Meta:
        verbose_name = 'Departman'
        verbose_name_plural = 'Departmanlar'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def managers(self):
        from identity.models import User, Role
        return (
            User.objects
            .filter(department=self, role=Role.MANAGER, is_active=True)
            .order_by('first_name', 'last_name', 'username')
        )


class Category(models.Model):

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='categories',
        verbose_name='Departman',
    )

    name = models.CharField(
        max_length=100,
        verbose_name='Kategori Adı',
    )

    description = models.TextField(
        blank=True,
        default='',
        verbose_name='Açıklama',
    )

    class Meta:
        verbose_name = 'Kategori'
        verbose_name_plural = 'Kategoriler'
        ordering = ['department', 'name']
        unique_together = ['department', 'name']

    def __str__(self):
        return f"{self.department.name} → {self.name}"
