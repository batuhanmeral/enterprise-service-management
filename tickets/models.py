from django.conf import settings
from django.db import models
from django.utils import timezone

from .validators import validate_file_extension, validate_file_size, validate_file_content


# Bilet durumlarını tanımlayan enumeration sınıfı
class Status(models.TextChoices):
    OPEN = 'OPEN', 'Açık'
    IN_PROGRESS = 'IN_PROGRESS', 'İşlemde'
    CLOSED = 'CLOSED', 'Kapalı'


# Bilet öncelik seviyelerini tanımlayan enumeration sınıfı
class Priority(models.TextChoices):
    LOW = 'LOW', 'Düşük'
    NORMAL = 'NORMAL', 'Normal'
    HIGH = 'HIGH', 'Yüksek'
    URGENT = 'URGENT', 'Acil'


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

    # Biletin mevcut durumu
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name='Durum',
    )

    # Biletin öncelik seviyesi
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.NORMAL,
        verbose_name='Öncelik',
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
        on_delete=models.SET_NULL,  # Kullanıcı silinse bile bilet sistemde kalır
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
        on_delete=models.SET_NULL,  # Departman silinse bile bilet sistemde kalır
        null=True,
        blank=True,
        related_name='tickets',
        verbose_name='Departman',
    )

    # Talebin alt kategorisi
    category = models.ForeignKey(
        'departments.Category',
        on_delete=models.SET_NULL,  # Kategori silinse bile bilet sistemde kalır
        null=True,
        blank=True,
        related_name='tickets',
        verbose_name='Kategori',
    )

    # Bilete eklenen etiketler (M2M)
    tags = models.ManyToManyField(
        'Tag',
        blank=True,
        related_name='tickets',
        verbose_name='Etiketler',
    )

    # Modelin admin paneli ve veritabanı davranışlarını belirleyen meta-veri sınıfı
    class Meta:
        verbose_name = 'Bilet'
        verbose_name_plural = 'Biletler'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['department', 'status'], name='ticket_dept_status_idx'),
            models.Index(fields=['sender'], name='ticket_sender_idx'),
            models.Index(fields=['assigned_to', 'status'], name='ticket_assigned_status_idx'),
            models.Index(fields=['status', 'closed_at'], name='ticket_status_closedat_idx'),
        ]

    # Model objesinin sistemde metin olarak nasıl temsil edileceğini belirleyen fonksiyon
    def __str__(self):
        return f"[{self.get_status_display()}] {self.subject} ({self.code})"

    # İnsan-okur bilet kodu — TIC-0001, TIC-0002, ... (oluşturma sırasına denk gelir).
    # pk auto-increment olduğundan eskiden yeniye doğru büyür; silinen kodlar yeniden kullanılmaz.
    @property
    def code(self):
        return f'TIC-{self.pk:04d}'

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

    # Kapalı bileti yeniden aç (talep sahibi veya Admin)
    def reopen(self):
        self.status = Status.OPEN
        self.assigned_to = None
        self.closed_at = None
        self.save(update_fields=['status', 'assigned_to', 'closed_at', 'updated_at'])

    # Bileti kapat ve çözüm notunu kaydet
    def close(self, resolution_note=''):
        self.status = Status.CLOSED
        self.resolution_note = resolution_note
        self.closed_at = timezone.now()
        self.save(update_fields=[
            'status', 'resolution_note', 'closed_at', 'updated_at',
        ])


# Etiket — biletleri serbest biçimli kategorize etmek için (M2M).
class Tag(models.Model):
    name = models.CharField(max_length=40, unique=True, verbose_name='Etiket')
    # CSS hex rengi — UI'da pill arka planı olarak kullanılır
    color = models.CharField(
        max_length=7, default='#6c757d',
        verbose_name='Renk',
        help_text='Hex format: #RRGGBB',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Etiket'
        verbose_name_plural = 'Etiketler'
        ordering = ['name']

    def __str__(self):
        return self.name


# Bilet eki — bir bilete birden fazla dosya eklenebilir
class TicketAttachment(models.Model):

    ticket = models.ForeignKey(
        'Ticket',
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Bilet',
    )

    file = models.FileField(
        upload_to='ticket_attachments/%Y/%m/',
        validators=[validate_file_extension, validate_file_size, validate_file_content],
        verbose_name='Dosya',
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_attachments',
        verbose_name='Yükleyen',
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Yükleme Tarihi',
    )

    class Meta:
        verbose_name = 'Bilet Eki'
        verbose_name_plural = 'Bilet Ekleri'
        ordering = ['uploaded_at']

    def __str__(self):
        import os
        return os.path.basename(self.file.name) if self.file else f'Ek #{self.pk}'

    @property
    def filename(self):
        import os
        return os.path.basename(self.file.name) if self.file else ''


# Bilet yorum/mesajlaşma modeli — talep sahibi ile personel diyaloğu
class TicketComment(models.Model):

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name='Bilet',
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='ticket_comments',
        verbose_name='Yazan',
    )

    content = models.TextField(
        max_length=2000,
        verbose_name='Yorum',
        blank=True,
    )

    attachment = models.FileField(
        upload_to='comment_attachments/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Dosya Eki',
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Tarih',
    )

    class Meta:
        verbose_name = 'Bilet Yorumu'
        verbose_name_plural = 'Bilet Yorumları'
        ordering = ['created_at']

    def __str__(self):
        author_name = self.author.username if self.author else 'Anonim'
        return f"#{self.ticket_id} — {author_name}: {self.content[:50]}"


# Bilet geçmişi — kimin, ne zaman, ne işlem yaptığını kaydeden audit log
class TicketHistory(models.Model):

    # İşlemin yapıldığı bilet
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,  # Bilet silinirse geçmişi de silinir
        related_name='history',
        verbose_name='Bilet',
    )

    # İşlemi yapan kullanıcı
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='ticket_actions',
        verbose_name='İşlemi Yapan',
    )

    # Yapılan işlemin açıklaması
    action = models.CharField(
        max_length=200,
        verbose_name='İşlem',
    )

    # İşlemin yapıldığı tarih
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='İşlem Tarihi',
    )

    # Modelin admin paneli ve veritabanı davranışlarını belirleyen meta-veri sınıfı
    class Meta:
        verbose_name = 'Bilet Geçmişi'
        verbose_name_plural = 'Bilet Geçmişleri'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['actor'], name='tickethist_actor_idx'),
            models.Index(fields=['ticket', '-created_at'], name='tickethist_ticket_created_idx'),
        ]

    # Model objesinin sistemde metin olarak nasıl temsil edileceğini belirleyen fonksiyon
    def __str__(self):
        actor_name = self.actor.username if self.actor else 'Sistem'
        return f"#{self.ticket_id} — {actor_name}: {self.action}"
