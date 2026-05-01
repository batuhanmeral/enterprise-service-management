import django.db.models.deletion
import tickets.validators
from django.conf import settings
from django.db import migrations, models


def copy_attachments_to_new_model(apps, schema_editor):
    """Mevcut Ticket.attachment dosyalarını TicketAttachment modeline kopyalar.

    Dosya yeniden upload edilmez — sadece DB kaydı oluşur ve aynı yolu işaret eder.
    Yükleyen olarak ticket.sender atanır (gerçek yükleyeni bilmiyoruz).
    """
    Ticket = apps.get_model('tickets', 'Ticket')
    TicketAttachment = apps.get_model('tickets', 'TicketAttachment')

    qs = Ticket.objects.exclude(attachment='').exclude(attachment__isnull=True)
    for ticket in qs:
        TicketAttachment.objects.create(
            ticket=ticket,
            file=ticket.attachment.name,  # mevcut dosya yolu
            uploaded_by_id=ticket.sender_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0005_add_db_indexes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1) Yeni modeli oluştur
        migrations.CreateModel(
            name='TicketAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='ticket_attachments/%Y/%m/', validators=[tickets.validators.validate_file_extension, tickets.validators.validate_file_size, tickets.validators.validate_file_content], verbose_name='Dosya')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True, verbose_name='Yükleme Tarihi')),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='tickets.ticket', verbose_name='Bilet')),
                ('uploaded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_attachments', to=settings.AUTH_USER_MODEL, verbose_name='Yükleyen')),
            ],
            options={
                'verbose_name': 'Bilet Eki',
                'verbose_name_plural': 'Bilet Ekleri',
                'ordering': ['uploaded_at'],
            },
        ),
        # 2) Eski tek-dosya ekleri yeni modele kopyala
        migrations.RunPython(copy_attachments_to_new_model, migrations.RunPython.noop),
        # 3) Eski alanı kaldır
        migrations.RemoveField(
            model_name='ticket',
            name='attachment',
        ),
    ]
