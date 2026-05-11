from django.db import migrations


# Eski Department.manager FK'sını silmeden önce mevcut yöneticileri MANAGER rolüne çevirip
# o departmana bağlı tutar — böylece yeni `managers` property'si onları yansıtır.
def ensure_manager_role_and_department(apps, schema_editor):
    Department = apps.get_model('departments', 'Department')
    User = apps.get_model('identity', 'User')

    for dept in Department.objects.all().iterator():
        manager_id = getattr(dept, 'manager_id', None)
        if not manager_id:
            continue
        try:
            user = User.objects.get(pk=manager_id)
        except User.DoesNotExist:
            continue
        # Rol ve departmanı senkronize et
        user.role = 'MANAGER'
        user.department = dept
        # is_staff senkronizasyonu (User modelinin save() override'ı çalışmaz historical model'de)
        user.save()


def noop_reverse(apps, schema_editor):
    # FK'yı geri ekleme imkanı yok — historical state'te manager_id kaybolmuş olur
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('departments', '0002_department_manager'),
    ]

    operations = [
        # 1. Önce mevcut manager FK değerlerini User.role + User.department'a aktar
        migrations.RunPython(ensure_manager_role_and_department, noop_reverse),
        # 2. Sonra FK'yı sil
        migrations.RemoveField(
            model_name='department',
            name='manager',
        ),
    ]
