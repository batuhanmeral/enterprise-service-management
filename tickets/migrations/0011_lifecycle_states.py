from django.db import migrations, models


def backfill_lifecycle(apps, schema_editor):
    """
    Eski tek-aşamalı CLOSED akışından yeni 4-aşamalı akışa geçiş:
      - CLOSED + resolution_confirmed=True  -> CLOSED kalır (nihai)
      - CLOSED + resolution_confirmed=None  -> RESOLVED'a alınır (onay bekleniyor)
                                                resolved_at = eski closed_at, closed_at temizlenir
      - CLOSED + resolution_confirmed=False -> IN_PROGRESS'e döndürülür (red sonrası işlem),
                                                reopen_count=1, closed_at temizlenir
    """
    Ticket = apps.get_model('tickets', 'Ticket')

    for t in Ticket.objects.filter(status='CLOSED'):
        if t.resolution_confirmed is True:
            # Zaten onaylanmış — durumu koru
            continue
        if t.resolution_confirmed is None:
            t.status = 'RESOLVED'
            t.resolved_at = t.closed_at
            t.closed_at = None
            t.save(update_fields=['status', 'resolved_at', 'closed_at'])
        else:  # False
            t.status = 'IN_PROGRESS'
            t.reopen_count = 1
            t.closed_at = None
            t.resolution_confirmed = None
            t.save(update_fields=['status', 'reopen_count', 'closed_at', 'resolution_confirmed'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0010_add_action_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='resolved_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Çözüldü Tarihi'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='reopen_count',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='Yeniden Açılma Sayısı'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='rejection_reason',
            field=models.TextField(blank=True, default='', verbose_name='Son Red Gerekçesi'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='escalated_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Eskalasyon Tarihi'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='csat_rating',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Memnuniyet Puanı'),
        ),
        migrations.RunPython(backfill_lifecycle, noop_reverse),
    ]
