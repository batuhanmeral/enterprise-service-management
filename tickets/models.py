from django.conf import settings
from django.db import models
from django.utils import timezone

from .validators import validate_file_extension, validate_file_size, validate_file_content


# Bilet durumlarını tanımlayan enumeration sınıfı
class Status(models.TextChoices):
    OPEN = 'OPEN', 'Açık'
    IN_PROGRESS = 'IN_PROGRESS', 'İşlemde'
    CLOSED = 'CLOSED', 'Kapalı'


# Kullanıcı taleplerini temsil eden model
class Ticket(models.Model):

    # Talebin konu başlığı
    subject = models.CharField(
        max_length=100,
        verbose_name='Konu',
    )

    # Talebin detaylı açıklaması
    message = models.TextField(
        max_length=1000,
        verbose_name='Mesaj',
    )

    # Talebe eklenen dosya (isteğe bağlı)
    attachment = models.FileField(
        upload_to='ticket_attachments/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Dosya Eki',
        validators=[validate_file_extension, validate_file_size, validate_file_content],
    )

    # Biletin mevcut durumu
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name='Durum',
    )

    # Bilet kapatılırken eklenen çözüm açıklaması
    resolution_note = models.TextField(
        blank=True,
        default='',
        verbose_name='Çözüm Notu',
    )

    # Biletin oluşturulma tarihi
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Oluşturulma Tarihi',
    )

    # Son güncelleme tarihi
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Son Güncelleme',
    )

    # Biletin kapatıldığı tarih ve saat
    closed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Kapatılma Tarihi',
    )

    # Talebi oluşturan kullanıcı
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Kullanıcı silinse bile bilet sistemde kalır
        null=True,
        related_name='sent_tickets',
        verbose_name='Talep Sahibi',
    )

    # Talebi üstlenen departman personeli
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tickets',
        verbose_name='Üstlenen Personel',
    )

    # Talebin yönlendirildiği departman
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.SET_NULL, # Departman silinse bile bilet sistemde kalır
        null=True,
        related_name='tickets',
        verbose_name='Departman',
    )

    # Talebin alt kategorisi
    category = models.ForeignKey(
        'departments.Category',
        on_delete=models.SET_NULL, # Kategori silinse bile bilet sistemde kalır
        null=True,
        blank=True,
        related_name='tickets',
        verbose_name='Kategori',
    )

    # Modelin admin paneli ve veritabanı davranışlarını belirleyen meta-veri sınıfı
    class Meta:
        verbose_name = 'Bilet'
        verbose_name_plural = 'Biletler'
        ordering = ['-created_at']

    # Model objesinin sistemde metin olarak nasıl temsil edileceğini belirleyen fonksiyon
    def __str__(self):
        return f"[{self.get_status_display()}] {self.subject} (#{self.pk})"

    # Talebi personelin üzerine al, durumu İŞLEMDE yap
    def take_into_process(self, personnel):
        self.assigned_to = personnel
        self.status = Status.IN_PROGRESS
        self.save(update_fields=['assigned_to', 'status', 'updated_at'])

    # Talebi başka bir departmana transfer et, durum AÇIK'a döner
    def transfer(self, new_department, new_category=None):
        self.department = new_department
        self.category = new_category
        self.assigned_to = None
        self.status = Status.OPEN
        self.save(update_fields=[
            'department', 'category', 'assigned_to', 'status', 'updated_at',
        ])

    # Bileti kapat ve çözüm notunu kaydet
    def close(self, resolution_note=''):
        self.status = Status.CLOSED
        self.resolution_note = resolution_note
        self.closed_at = timezone.now()
        self.save(update_fields=[
            'status', 'resolution_note', 'closed_at', 'updated_at',
        ])
