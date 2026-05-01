from django.db import migrations


def sync_admin_is_staff(apps, schema_editor):
    """ADMIN rolündeki kullanıcılara Django admin (is_staff) erişimi ver."""
    User = apps.get_model('identity', 'User')
    User.objects.filter(role='ADMIN', is_staff=False).update(is_staff=True)


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0004_alter_user_avatar'),
    ]

    operations = [
        migrations.RunPython(sync_admin_is_staff, migrations.RunPython.noop),
    ]
