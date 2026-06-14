from django.conf import settings
from django.db import models

class Notification(models.Model):

    message = models.TextField(
        verbose_name='Bildirim Mesajı',
    )

    is_read = models.BooleanField(
        default=False,
        verbose_name='Okundu mu?',
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Oluşturulma Tarihi',
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Alıcı',
    )

    ticket = models.ForeignKey(
        'tickets.Ticket',
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='İlgili Bilet',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Bildirim'
        verbose_name_plural = 'Bildirimler'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read'], name='notif_recipient_isread_idx'),
            models.Index(fields=['recipient', '-created_at'], name='notif_recipient_created_idx'),
        ]

    def __str__(self):
        status = "✓" if self.is_read else "✉"
        return f"[{status}] {self.recipient.username}: {self.message[:50]}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])
