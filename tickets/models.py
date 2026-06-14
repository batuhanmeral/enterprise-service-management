from datetime import time, timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from .validators import validate_file_extension, validate_file_size, validate_file_content


class Status(models.TextChoices):
    OPEN = 'OPEN', 'Açık'
    IN_PROGRESS = 'IN_PROGRESS', 'İşlemde'
    RESOLVED = 'RESOLVED', 'Çözüldü'
    CLOSED = 'CLOSED', 'Kapandı'
    ESCALATED = 'ESCALATED', 'Eskalasyon'


MAX_REOPENS = 2
AUTO_CLOSE_DAYS = 3

MAX_ACTIVE_TICKETS_PER_AGENT = 5


class Priority(models.TextChoices):
    LOW = 'LOW', 'Düşük'
    NORMAL = 'NORMAL', 'Normal'
    HIGH = 'HIGH', 'Yüksek'
    URGENT = 'URGENT', 'Acil'


SLA_HOURS = {
    Priority.URGENT: 4,
    Priority.HIGH: 24,
    Priority.NORMAL: 72,
    Priority.LOW: 168,
}

WORK_DAY_START = time(9, 0)
WORK_DAY_END = time(18, 0)
WORK_DAYS = frozenset({0, 1, 2, 3, 4})


def _next_work_day_start(dt):
    nxt = (dt + timedelta(days=1)).replace(
        hour=WORK_DAY_START.hour, minute=WORK_DAY_START.minute, second=0, microsecond=0
    )
    return nxt


def add_business_hours(start, hours):
    remaining = timedelta(hours=hours)
    cur = timezone.localtime(start)
    while remaining > timedelta(0):
        if cur.weekday() not in WORK_DAYS:
            cur = _next_work_day_start(cur)
            continue
        day_start = cur.replace(hour=WORK_DAY_START.hour, minute=WORK_DAY_START.minute, second=0, microsecond=0)
        day_end = cur.replace(hour=WORK_DAY_END.hour, minute=WORK_DAY_END.minute, second=0, microsecond=0)
        if cur < day_start:
            cur = day_start
        if cur >= day_end:
            cur = _next_work_day_start(cur)
            continue
        available = day_end - cur
        if remaining <= available:
            return cur + remaining
        remaining -= available
        cur = _next_work_day_start(cur)
    return cur


def business_seconds_between(start, end):
    start = timezone.localtime(start)
    end = timezone.localtime(end)
    if end <= start:
        return 0
    total = 0.0
    cur = start
    while cur < end:
        if cur.weekday() in WORK_DAYS:
            day_start = cur.replace(hour=WORK_DAY_START.hour, minute=WORK_DAY_START.minute, second=0, microsecond=0)
            day_end = cur.replace(hour=WORK_DAY_END.hour, minute=WORK_DAY_END.minute, second=0, microsecond=0)
            seg_start = max(cur, day_start)
            seg_end = min(end, day_end)
            if seg_end > seg_start:
                total += (seg_end - seg_start).total_seconds()
        cur = (cur + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return total


class Ticket(models.Model):

    subject = models.CharField(
        max_length=100,
        verbose_name='Konu',
    )

    message = models.TextField(
        max_length=1000,
        verbose_name='Mesaj',
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name='Durum',
    )

    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.NORMAL,
        verbose_name='Öncelik',
    )

    resolution_note = models.TextField(
        blank=True,
        default='',
        verbose_name='Çözüm Notu',
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Oluşturulma Tarihi',
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Son Güncelleme',
    )

    closed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Kapatılma Tarihi',
    )

    sla_due_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='SLA Hedef Tarihi',
    )

    resolution_confirmed = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name='Çözüm Onayı',
    )

    resolved_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Çözüldü Tarihi',
    )

    reopen_count = models.PositiveSmallIntegerField(
        default=0,
        verbose_name='Yeniden Açılma Sayısı',
    )

    rejection_reason = models.TextField(
        blank=True,
        default='',
        verbose_name='Son Red Gerekçesi',
    )

    escalated_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Eskalasyon Tarihi',
    )

    csat_rating = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        verbose_name='Memnuniyet Puanı',
    )

    sla_warning_sent_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='SLA Uyarısı Gönderildi',
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_tickets',
        verbose_name='Talep Sahibi',
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tickets',
        verbose_name='Üstlenen Personel',
    )

    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets',
        verbose_name='Departman',
    )

    category = models.ForeignKey(
        'departments.Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets',
        verbose_name='Kategori',
    )

    tags = models.ManyToManyField(
        'Tag',
        blank=True,
        related_name='tickets',
        verbose_name='Etiketler',
    )

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

    def __str__(self):
        return f"[{self.get_status_display()}] {self.subject} ({self.code})"

    def save(self, *args, **kwargs):
        anchor = self.created_at or timezone.now()
        hours = SLA_HOURS.get(self.priority, SLA_HOURS[Priority.NORMAL])
        self.sla_due_at = add_business_hours(anchor, hours)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'priority' in set(update_fields):
            kwargs['update_fields'] = list(set(update_fields) | {'sla_due_at'})
        super().save(*args, **kwargs)

    @property
    def code(self):
        return f'TIC-{self.pk:04d}'

    @property
    def is_overdue(self):
        if self.status in (Status.RESOLVED, Status.CLOSED, Status.ESCALATED):
            return False
        if not self.sla_due_at:
            return False
        return timezone.now() > self.sla_due_at

    @property
    def auto_close_due_at(self):
        if self.status != Status.RESOLVED or not self.resolved_at:
            return None
        return self.resolved_at + timedelta(days=AUTO_CLOSE_DAYS)

    @property
    def is_locked(self):
        return self.status in (Status.CLOSED, Status.ESCALATED)

    @property
    def reopen_limit_reached(self):
        return self.reopen_count >= MAX_REOPENS

    @property
    def sla_progress_pct(self):
        if not self.created_at:
            return 0
        target_seconds = SLA_HOURS.get(self.priority, SLA_HOURS[Priority.NORMAL]) * 3600
        elapsed = business_seconds_between(self.created_at, timezone.now())
        return min(int(elapsed / target_seconds * 100), 200) if target_seconds else 0

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
        if minutes and not days:
            parts.append(f'{minutes} dk')
        return ' '.join(parts) if parts else '< 1 dk'

    def take_into_process(self, personnel):
        self.assigned_to = personnel
        self.status = Status.IN_PROGRESS
        self.save(update_fields=['assigned_to', 'status', 'updated_at'])

    def auto_assign(self):
        from django.db.models import Count, Q
        from departments.models import Department
        from identity.models import Role, User
        if not self.department_id:
            return None
        with transaction.atomic():
            dept = Department.objects.select_for_update().get(pk=self.department_id)
            if not dept.auto_assign_enabled:
                return None
            agents = list(
                User.objects
                .filter(department_id=dept.pk, role=Role.AGENT, is_active=True)
                .exclude(pk=self.sender_id)
                .annotate(active_load=Count(
                    'assigned_tickets',
                    filter=Q(assigned_tickets__status=Status.IN_PROGRESS),
                ))
                .order_by('pk')
            )
            agents = [a for a in agents if a.active_load < MAX_ACTIVE_TICKETS_PER_AGENT]
            if not agents:
                return None
            min_load = min(a.active_load for a in agents)
            candidates = [a for a in agents if a.active_load == min_load]
            last_id = dept.last_auto_assigned_id
            personnel = next(
                (a for a in candidates if last_id is not None and a.pk > last_id),
                candidates[0],
            )
            self.take_into_process(personnel)
            dept.last_auto_assigned = personnel
            dept.save(update_fields=['last_auto_assigned', 'updated_at'])
        return personnel

    def transfer(self, new_department, new_category=None):
        self.department = new_department
        self.category = new_category
        self.assigned_to = None
        self.status = Status.OPEN
        self.save(update_fields=[
            'department', 'category', 'assigned_to', 'status', 'updated_at',
        ])

    def reopen(self):
        self.status = Status.OPEN
        self.assigned_to = None
        self.closed_at = None
        self.resolved_at = None
        self.resolution_confirmed = None
        self.reopen_count = 0
        self.rejection_reason = ''
        self.escalated_at = None
        self.save(update_fields=[
            'status', 'assigned_to', 'closed_at', 'resolved_at',
            'resolution_confirmed', 'reopen_count', 'rejection_reason',
            'escalated_at', 'updated_at',
        ])

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

    def confirm_resolution(self):
        self.status = Status.CLOSED
        self.resolution_confirmed = True
        self.closed_at = timezone.now()
        self.save(update_fields=[
            'status', 'resolution_confirmed', 'closed_at', 'updated_at',
        ])

    def auto_close(self):
        self.status = Status.CLOSED
        self.resolution_confirmed = True
        self.closed_at = timezone.now()
        self.save(update_fields=[
            'status', 'resolution_confirmed', 'closed_at', 'updated_at',
        ])

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

    def escalate(self, reason=''):
        self.status = Status.ESCALATED
        self.escalated_at = timezone.now()
        if reason:
            self.rejection_reason = reason
        self.save(update_fields=[
            'status', 'escalated_at', 'rejection_reason', 'updated_at',
        ])

    def set_csat(self, rating):
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError('CSAT puanı 1-5 arasında olmalı')
        if self.status != Status.CLOSED:
            raise ValueError('CSAT yalnızca kapanmış bilet için verilebilir')
        self.csat_rating = rating
        self.save(update_fields=['csat_rating', 'updated_at'])


class Tag(models.Model):
    name = models.CharField(max_length=40, unique=True, verbose_name='Etiket')
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


class TicketHistory(models.Model):

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name='history',
        verbose_name='Bilet',
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='ticket_actions',
        verbose_name='İşlemi Yapan',
    )

    action = models.CharField(
        max_length=200,
        verbose_name='İşlem',
    )

    action_type = models.CharField(
        max_length=30,
        choices=TicketActionType.choices,
        default=TicketActionType.OTHER,
        verbose_name='Aksiyon Tipi',
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='İşlem Tarihi',
    )

    class Meta:
        verbose_name = 'Bilet Geçmişi'
        verbose_name_plural = 'Bilet Geçmişleri'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['actor'], name='tickethist_actor_idx'),
            models.Index(fields=['ticket', '-created_at'], name='tickethist_ticket_created_idx'),
            models.Index(fields=['action_type', 'actor'], name='tickethist_type_actor_idx'),
        ]

    def __str__(self):
        actor_name = self.actor.username if self.actor else 'Sistem'
        return f"#{self.ticket_id} — {actor_name}: {self.action}"
