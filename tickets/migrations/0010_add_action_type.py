from django.db import migrations, models


# Mevcut kayıtları action text prefix'inden enum tipine yükseltir.
# Bu son kez prefix matching yapılır; bundan sonra tüm yeni kayıtlar action_type ile gelir.
PREFIX_TO_TYPE = [
    ('Bilet oluşturuldu', 'CREATED'),
    ('Bilet kapatıldı', 'CLOSED'),
    ('Bilet yeniden açıldı', 'REOPENED'),
    ('Bilet çözümsüz olarak yeniden açıldı', 'RESOLUTION_REJECTED'),
    ('Talep sahibi sorununun çözüldüğünü onayladı', 'RESOLUTION_CONFIRMED'),
    ('Talep sahibi sorununun çözülmediğini bildirdi', 'RESOLUTION_REJECTED'),
    ('Bilet güncellendi', 'UPDATED'),
    ('Bilet ', 'TRANSFERRED'),     # "Bilet X -> Y departmanına transfer edildi"
    ('Atama kaldırıldı', 'UNASSIGNED'),
]


def backfill_action_type(apps, schema_editor):
    TicketHistory = apps.get_model('tickets', 'TicketHistory')
    for h in TicketHistory.objects.all().iterator():
        a = h.action or ''
        new_type = 'OTHER'
        # Üstlen / atama özel kontrol — text içerebilir
        if 'üstlendi' in a:
            new_type = 'TAKEN'
        elif 'personeline atandı' in a:
            new_type = 'ASSIGNED'
        else:
            for prefix, t in PREFIX_TO_TYPE:
                if a.startswith(prefix):
                    new_type = t
                    break
        h.action_type = new_type
        h.save(update_fields=['action_type'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0009_add_resolution_confirmed'),
    ]

    operations = [
        migrations.AddField(
            model_name='tickethistory',
            name='action_type',
            field=models.CharField(
                choices=[
                    ('CREATED', 'Bilet oluşturuldu'),
                    ('TAKEN', 'Bilet üstlenildi'),
                    ('ASSIGNED', 'Personel atandı'),
                    ('UNASSIGNED', 'Atama kaldırıldı'),
                    ('CLOSED', 'Bilet kapatıldı'),
                    ('REOPENED', 'Bilet yeniden açıldı'),
                    ('TRANSFERRED', 'Bilet transfer edildi'),
                    ('UPDATED', 'Bilet güncellendi'),
                    ('RESOLUTION_CONFIRMED', 'Çözüm onaylandı'),
                    ('RESOLUTION_REJECTED', 'Çözüm reddedildi'),
                    ('OTHER', 'Diğer'),
                ],
                default='OTHER',
                max_length=30,
                verbose_name='Aksiyon Tipi',
            ),
        ),
        migrations.RunPython(backfill_action_type, noop_reverse),
        migrations.AddIndex(
            model_name='tickethistory',
            index=models.Index(
                fields=['action_type', 'actor'],
                name='tickethist_type_actor_idx',
            ),
        ),
    ]
