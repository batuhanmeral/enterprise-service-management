from django.db import models


# Kurumdaki departmanları temsil eden model
class Department(models.Model):

    # Departmanın adı
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Departman Adı',
    )

    # Departmanı tanımlayan açıklama
    description = models.TextField(
        max_length=1000,
        blank=True,
        default='',
        verbose_name='Açıklama',
    )

    # Departmanın sisteme eklendiği tarih
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Oluşturulma Tarihi',
    )

    # Son güncelleme tarihi
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Güncellenme Tarihi',
    )

    # Modelin admin paneli ve veritabanı davranışlarını belirleyen meta-veri sınıfı
    class Meta:
        verbose_name = 'Departman'
        verbose_name_plural = 'Departmanlar'
        ordering = ['name']

    # Model objesinin sistemde metin olarak nasıl temsil edileceğini belirleyen fonksiyon
    def __str__(self):
        return self.name


# Departmana ait talep alt kategorisi
class Category(models.Model):

    # Kategorinin ait olduğu departman
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,  # Departman silinince kategoriler de silinir
        related_name='categories',
        verbose_name='Departman',
    )

    # Talep alt başlığı
    name = models.CharField(
        max_length=100,
        verbose_name='Kategori Adı',
    )

    # Kategorinin açıklama metni
    description = models.TextField(
        blank=True,
        default='',
        verbose_name='Açıklama',
    )

    # Modelin admin paneli ve veritabanı davranışlarını belirleyen meta-veri sınıfı
    class Meta:
        verbose_name = 'Kategori'
        verbose_name_plural = 'Kategoriler'
        ordering = ['department', 'name']
        unique_together = ['department', 'name']

    # Model objesinin sistemde metin olarak nasıl temsil edileceğini belirleyen fonksiyon
    def __str__(self):
        return f"{self.department.name} → {self.name}"
