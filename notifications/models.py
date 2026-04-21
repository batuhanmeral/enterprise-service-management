from django.conf import settings
from django.db import models

# Kullanıcıya gönderilecek bildirimleri temsil eden model
class Notification(models.Model):

    # Kullanıcıya gösterilecek bildirim metni
    message = models.TextField(
        verbose_name='Bildirim Mesajı',
    )

    # Bildirimin okunup okunmadığı
    is_read = models.BooleanField(
        default=False,
        verbose_name='Okundu mu?',
    )

    # Bildirimin oluşturulma tarihi
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Oluşturulma Tarihi',
    )

    # Bildirimi alan kullanıcı
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE, # Kullanıcı silinirse bildirimleri de silinir
        related_name='notifications',
        verbose_name='Alıcı',
    )

    # Bildirimi tetikleyen bilet
    ticket = models.ForeignKey(
        'tickets.Ticket',
        on_delete=models.CASCADE, # Bilet silinirse bildirimleri de silinir
        related_name='notifications',
        verbose_name='İlgili Bilet',
    )

    # Modelin admin paneli ve veritabanı davranışlarını belirleyen meta-veri sınıfı
    class Meta:
        verbose_name = 'Bildirim'
        verbose_name_plural = 'Bildirimler'
        ordering = ['-created_at']

    # Model objesinin sistemde metin olarak nasıl temsil edileceğini belirleyen fonksiyon
    def __str__(self):
        status = "✓" if self.is_read else "✉"
        return f"[{status}] {self.recipient.username}: {self.message[:50]}"

    # Bildirimi okundu olarak işaretle
    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])
