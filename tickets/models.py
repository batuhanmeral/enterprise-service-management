from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from .validators import validate_file_extension, validate_file_size, validate_file_content


# Bilet durumlarını tanımlayan enumeration sınıfı
class Status(models.TextChoices):
    OPEN = 'OPEN', 'Açık'
    IN_PROGRESS = 'IN_PROGRESS', 'İşlemde'
    RESOLVED = 'RESOLVED', 'Çözüldü'      # Personel çözdü — talep sahibinin onayı bekleniyor
    CLOSED = 'CLOSED', 'Kapandı'          # Talep sahibi onayladı veya 3 günde otomatik kapandı (kilitli)
    ESCALATED = 'ESCALATED', 'Eskalasyon' # 3. kez reddedildi — yönetici müdahalesi gerekiyor


# Yaşam döngüsü sabitleri
MAX_REOPENS = 2          # 3. kez başarısız olduğunda ESCALATED'a geçilir
AUTO_CLOSE_DAYS = 3      # RESOLVED durumda 3 gün boyunca onaysız kalan biletler otomatik kapanır


# Bilet öncelik seviyelerini tanımlayan enumeration sınıfı
class Priority(models.TextChoices):
    LOW = 'LOW', 'Düşük'
    NORMAL = 'NORMAL', 'Normal'
    HIGH = 'HIGH', 'Yüksek'
    URGENT = 'URGENT', 'Acil'


# SLA çözüm hedefleri — önceliğe göre saat cinsinden taahhüt
SLA_HOURS = {
    Priority.URGENT: 4,
    Priority.HIGH: 24,
    Priority.NORMAL: 72,
    Priority.LOW: 168,
}


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

    # Talep sahibinin çözüm onayı: None=Bekleniyor, True=Onaylandı, False=Reddedildi
    resolution_confirmed = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name='Çözüm Onayı',
    )

    # Personelin biletini çözdü olarak işaretlediği tarih (RESOLVED -> CLOSED ya da auto-close için temel)
    resolved_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Çözüldü Tarihi',
    )

    # Biletin kaç kez reddedildiği — MAX_REOPENS aşılırsa ESCALATED'a geçer
    reopen_count = models.PositiveSmallIntegerField(
        default=0,
        verbose_name='Yeniden Açılma Sayısı',
    )

    # Talep sahibinin son red gerekçesi (önceki redler TicketHistory'de tutulur)
    rejection_reason = models.TextField(
        blank=True,
        default='',
        verbose_name='Son Red Gerekçesi',
    )

    # Eskalasyona alındığı tarih
    escalated_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Eskalasyon Tarihi',
    )

    # Memnuniyet puanı (CSAT) — talep sahibi 1-5 arası verir, sadece CLOSED'da geçerli
    csat_rating = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        verbose_name='Memnuniyet Puanı',
    )

    # SLA proaktif uyarısı: %75 eşiğinde bir kez gönderilen bildirimin tarih/saat'i.
    # null = henüz uyarı gönderilmedi. Cron komutu (`notify_sla_warnings`) bu alanı
    # set ederek aynı bilete tekrar uyarı gönderilmesini engeller.
    sla_warning_sent_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='SLA Uyarısı Gönderildi',
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

    # SLA hedef tarihi — önceliğe göre created_at + saat
    @property
    def sla_due_at(self):
        if not self.created_at:
            return None
        hours = SLA_HOURS.get(self.priority, SLA_HOURS[Priority.NORMAL])
        return self.created_at + timedelta(hours=hours)

    # Bilet aktif çalışma durumundan çıkmışsa SLA dışı sayılır
    # (RESOLVED/CLOSED/ESCALATED — sorun çözüm sürecini terk etmiştir)
    @property
    def is_overdue(self):
        if self.status in (Status.RESOLVED, Status.CLOSED, Status.ESCALATED):
            return False
        if not self.sla_due_at:
            return False
        return timezone.now() > self.sla_due_at

    # Talep sahibinin RESOLVED biletini onaylaması için son tarih (RESOLVED + AUTO_CLOSE_DAYS)
    @property
    def auto_close_due_at(self):
        if self.status != Status.RESOLVED or not self.resolved_at:
            return None
        return self.resolved_at + timedelta(days=AUTO_CLOSE_DAYS)

    # Bilet kilitli mi? CLOSED veya ESCALATED — düzenleme/yorum dışı işlemler engellenir
    @property
    def is_locked(self):
        return self.status in (Status.CLOSED, Status.ESCALATED)

    # Talep sahibi yeni bir red işlemi yaparsa eskalasyona geçecek mi?
    @property
    def reopen_limit_reached(self):
        return self.reopen_count >= MAX_REOPENS

    # SLA tükenmiş süre yüzdesi (0-100+) — UI'de progress bar için kullanışlı
    @property
    def sla_progress_pct(self):
        if not self.created_at:
            return 0
        hours = SLA_HOURS.get(self.priority, SLA_HOURS[Priority.NORMAL])
        elapsed = (timezone.now() - self.created_at).total_seconds() / 3600
        return min(int(elapsed / hours * 100), 200) if hours else 0

    # Bilet IN_PROGRESS durumunda toplam ne kadar süre aktif olarak çalışıldı?
    # TicketHistory aksiyonlarından otomatik hesaplanır — manuel girdi yok.
    # ENTER aksiyonları: TAKEN, ASSIGNED, REOPENED, RESOLUTION_REJECTED (red sonrası IN_PROGRESS'e döner)
    # EXIT aksiyonları: UNASSIGNED, RESOLVED, CLOSED, AUTO_CLOSED, ESCALATED, TRANSFERRED
    # Hâlâ IN_PROGRESS ise şimdiye kadar geçen süre eklenir (canlı sayar).
    @property
    def work_duration(self):
        from django.db.models import Q
        enter_types = {
            TicketActionType.TAKEN, TicketActionType.ASSIGNED,
            TicketActionType.REOPENED, TicketActionType.RESOLUTION_REJECTED,
        }
        exit_types = {
            TicketActionType.UNASSIGNED, TicketActionType.RESOLVED,
            TicketActionType.CLOSED, TicketActionType.AUTO_CLOSED,
            TicketActionType.ESCALATED, TicketActionType.TRANSFERRED,
        }
        events = self.history.filter(
            Q(action_type__in=enter_types) | Q(action_type__in=exit_types),
        ).order_by('created_at').values_list('action_type', 'created_at')

        total = timedelta(0)
        in_progress_since = None
        for action_type, created_at in events:
            if action_type in enter_types:
                if in_progress_since is None:
                    in_progress_since = created_at
            elif action_type in exit_types:
                if in_progress_since is not None:
                    total += created_at - in_progress_since
                    in_progress_since = None

        if in_progress_since is not None and self.status == Status.IN_PROGRESS:
            total += timezone.now() - in_progress_since
        return total

    # work_duration'ı insan-okur biçime çevir: "2 saat 15 dk", "3 gün 4 saat", "—" (yok).
    @property
    def work_duration_label(self):
        d = self.work_duration
        secs = int(d.total_seconds())
        if secs <= 0:
            return '—'
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        parts = []
        if days:
            parts.append(f'{days} gün')
        if hours:
            parts.append(f'{hours} saat')
        if minutes and not days:  # gün varken dakikayı atla, sadelik için
            parts.append(f'{minutes} dk')
        return ' '.join(parts) if parts else '< 1 dk'

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

    # Kapalı bileti yeniden aç (Admin override) — sayaçları sıfırlar, normal akışın dışıdır
    def reopen(self):
        self.status = Status.OPEN
        self.assigned_to = None
        self.closed_at = None
        self.resolved_at = None
        self.resolution_confirmed = None
        self.save(update_fields=[
            'status', 'assigned_to', 'closed_at', 'resolved_at',
            'resolution_confirmed', 'updated_at',
        ])

    # Personel: bileti çözdü olarak işaretler — RESOLVED durumuna geçer, talep sahibinin onayı beklenir.
    # Nihai kapanma DEĞİLDİR; auto-close veya kullanıcı onayıyla CLOSED'a geçer.
    def mark_resolved(self, resolution_note=''):
        self.status = Status.RESOLVED
        self.resolution_note = resolution_note
        self.resolved_at = timezone.now()
        self.resolution_confirmed = None
        self.closed_at = None
        self.save(update_fields=[
            'status', 'resolution_note', 'resolved_at',
            'resolution_confirmed', 'closed_at', 'updated_at',
        ])

    # Talep sahibi çözümü onayladı — bilet CLOSED, kilitli, salt-okunur.
    def confirm_resolution(self):
        self.status = Status.CLOSED
        self.resolution_confirmed = True
        self.closed_at = timezone.now()
        self.save(update_fields=[
            'status', 'resolution_confirmed', 'closed_at', 'updated_at',
        ])

    # 3 günlük süre dolmuş RESOLVED bileti otomatik kapanış (sistem tarafından).
    def auto_close(self):
        self.status = Status.CLOSED
        self.resolution_confirmed = True
        self.closed_at = timezone.now()
        self.save(update_fields=[
            'status', 'resolution_confirmed', 'closed_at', 'updated_at',
        ])

    # Talep sahibi çözümü reddetti — gerekçe zorunlu.
    # MAX_REOPENS aşılmadıysa: bilet IN_PROGRESS'e döner, reopen_count++.
    # Aşıldıysa: ESCALATED'a geçer (yönetici müdahalesi gerekir).
    # Returns: True if reopened, False if escalated.
    def reject_resolution(self, reason):
        if not reason or not reason.strip():
            raise ValueError('Red gerekçesi zorunlu')
        new_count = self.reopen_count + 1
        if new_count > MAX_REOPENS:
            self.escalate(reason=reason.strip())
            return False
        self.reopen_count = new_count
        self.rejection_reason = reason.strip()
        self.status = Status.IN_PROGRESS
        self.resolution_confirmed = False
        self.resolved_at = None
        self.save(update_fields=[
            'reopen_count', 'rejection_reason', 'status',
            'resolution_confirmed', 'resolved_at', 'updated_at',
        ])
        return True

    # Bilet eskalasyona alınır — kilitlenir, yönetici tarafından ele alınmalıdır.
    def escalate(self, reason=''):
        self.status = Status.ESCALATED
        self.escalated_at = timezone.now()
        if reason:
            self.rejection_reason = reason
        self.save(update_fields=[
            'status', 'escalated_at', 'rejection_reason', 'updated_at',
        ])

    # Memnuniyet puanı kaydet (1-5). Sadece CLOSED bilette mantıklı.
    def set_csat(self, rating):
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError('CSAT puanı 1-5 arasında olmalı')
        if self.status != Status.CLOSED:
            raise ValueError('CSAT yalnızca kapanmış bilet için verilebilir')
        self.csat_rating = rating
        self.save(update_fields=['csat_rating', 'updated_at'])


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


# Bilet aksiyon tipleri — i18n veya text değişikliklerinden bağımsız sorgulanabilir
class TicketActionType(models.TextChoices):
    CREATED = 'CREATED', 'Bilet oluşturuldu'
    TAKEN = 'TAKEN', 'Bilet üstlenildi'
    ASSIGNED = 'ASSIGNED', 'Personel atandı'
    UNASSIGNED = 'UNASSIGNED', 'Atama kaldırıldı'
    RESOLVED = 'RESOLVED', 'Bilet çözüldü olarak işaretlendi'
    CLOSED = 'CLOSED', 'Bilet kapatıldı'
    AUTO_CLOSED = 'AUTO_CLOSED', 'Bilet otomatik kapatıldı'
    REOPENED = 'REOPENED', 'Bilet yeniden açıldı'
    ESCALATED = 'ESCALATED', 'Bilet eskalasyona alındı'
    TRANSFERRED = 'TRANSFERRED', 'Bilet transfer edildi'
    UPDATED = 'UPDATED', 'Bilet güncellendi'
    RESOLUTION_CONFIRMED = 'RESOLUTION_CONFIRMED', 'Çözüm onaylandı'
    RESOLUTION_REJECTED = 'RESOLUTION_REJECTED', 'Çözüm reddedildi'
    CSAT_RATED = 'CSAT_RATED', 'Memnuniyet puanlandı'
    OTHER = 'OTHER', 'Diğer'


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

    # Yapılan işlemin açıklaması (insan-okur)
    action = models.CharField(
        max_length=200,
        verbose_name='İşlem',
    )

    # Aksiyonun tipi — string-prefix yerine enum sorgulama için
    action_type = models.CharField(
        max_length=30,
        choices=TicketActionType.choices,
        default=TicketActionType.OTHER,
        verbose_name='Aksiyon Tipi',
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
            models.Index(fields=['action_type', 'actor'], name='tickethist_type_actor_idx'),
        ]

    # Model objesinin sistemde metin olarak nasıl temsil edileceğini belirleyen fonksiyon
    def __str__(self):
        actor_name = self.actor.username if self.actor else 'Sistem'
        return f"#{self.ticket_id} — {actor_name}: {self.action}"
