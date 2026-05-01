"""Demo veri yükleme komutu.

Kullanım:
    python manage.py seed_demo                # mevcut verileri korur, ekler
    python manage.py seed_demo --reset        # önceki demo verileri temizleyip yeniden oluşturur
    python manage.py seed_demo --tickets 60   # bilet sayısını özelleştir
    python manage.py seed_demo --users 30     # toplam çalışan/personel sayısını özelleştir

Oluşturulanlar:
- 1 süperkullanıcı (admin / admin123)
- 5+ departman + her birine 3-5 kategori
- 5+ etiket
- ~30 kullanıcı (1 admin, 5 manager, 8 agent, ~16 employee) — şifre: pass123
- ~25 bilet (rastgele durum/öncelik/atama, bazılarına yorum ve geçmiş kaydı)
- Bildirimler ve audit log kayıtları
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from departments.models import Department, Category
from tickets.models import Ticket, Status, Priority, Tag, TicketComment, TicketHistory
from notifications.models import Notification
from identity.models import Role, AuditLog


User = get_user_model()


DEPARTMENTS = [
    ('Bilgi İşlem', 'Donanım, yazılım, ağ ve sistem destek talepleri.', [
        'Donanım Arızası', 'Yazılım Kurulum', 'Ağ Sorunu', 'E-posta', 'VPN Erişim', 'Yazıcı'
    ]),
    ('İnsan Kaynakları', 'İzin, bordro ve özlük işlemleri.', [
        'İzin Talebi', 'Bordro', 'Özlük Belgeleri', 'İşe Alım', 'Eğitim'
    ]),
    ('Muhasebe', 'Fatura, ödeme ve mali raporlar.', [
        'Fatura Sorgu', 'Ödeme Takibi', 'Vergi', 'Masraf Beyanı'
    ]),
    ('İdari İşler', 'Ofis, lojistik ve genel idari talepler.', [
        'Ofis Malzemesi', 'Temizlik', 'Ulaşım', 'Yemekhane'
    ]),
    ('Pazarlama', 'Kampanya, reklam ve içerik talepleri.', [
        'Kampanya Talebi', 'Görsel Tasarım', 'Sosyal Medya', 'Etkinlik'
    ]),
    ('Hukuk', 'Sözleşme, dava ve hukuki danışmanlık.', [
        'Sözleşme İncelemesi', 'Dava Takibi', 'KVKK'
    ]),
]


TAGS = [
    ('Donanım', '#198754'),
    ('Yazılım', '#0dcaf0'),
    ('Ağ / İnternet', '#0d6efd'),
    ('Erişim Talebi', '#6f42c1'),
    ('İç Talep', '#20c997'),
    ('Tekrar Eden', '#fd7e14'),
    ('Eğitim', '#e83e8c'),
    ('Müşteri', '#6c757d'),
    ('Güvenlik', '#dc3545'),
    ('Raporlama', '#ffc107'),
]


SUBJECT_TEMPLATES = {
    'Donanım Arızası': ['Bilgisayar açılmıyor', 'Klavyenin tuşları çalışmıyor', 'Monitör ekranda titreme yapıyor', 'Mouse tepki vermiyor'],
    'Yazılım Kurulum': ['Office kurulumu', 'AutoCAD lisans aktivasyonu', 'Adobe paketleri yüklenecek'],
    'Ağ Sorunu': ['İnternet bağlantısı kopuyor', 'WiFi sinyali zayıf', 'Sunucuya erişemiyorum'],
    'E-posta': ['Outlook açılmıyor', 'E-postalar gelmiyor', 'Spam filtresi sorunlu'],
    'VPN Erişim': ['VPN bağlantısı kurulmuyor', 'VPN sertifikası süresi dolmuş'],
    'Yazıcı': ['Yazıcı kağıt sıkıştırıyor', 'Toner bitti', 'Yazıcı ağda görünmüyor'],
    'İzin Talebi': ['Yıllık izin talebi', 'Mazeret izni', 'Doğum izni hakkında'],
    'Bordro': ['Maaş bordrom hatalı', 'Geçen ayın bordrosunu alamadım'],
    'Özlük Belgeleri': ['İşveren yazısı talep ediyorum', 'Hizmet belgesi'],
    'İşe Alım': ['Açık pozisyon hakkında bilgi', 'CV gönderim'],
    'Eğitim': ['Online eğitim talebi', 'Sertifika programı'],
    'Fatura Sorgu': ['Geçen ayın faturası gelmedi', 'Faturada hata var'],
    'Ödeme Takibi': ['Ödememiz görünmüyor', 'Mutabakat'],
    'Vergi': ['KDV beyannamesi', 'Stopaj kesintisi'],
    'Masraf Beyanı': ['Yol masrafı', 'Yemek fişi onayı'],
    'Ofis Malzemesi': ['Kalem, defter siparişi', 'Yeni masa talebi'],
    'Temizlik': ['Tuvaletler kirli', 'Camların temizlenmesi'],
    'Ulaşım': ['Servis güzergahı değişikliği', 'Otopark talebi'],
    'Yemekhane': ['Menü talebi', 'Vejetaryen seçenek'],
    'Kampanya Talebi': ['Yıl sonu kampanyası planı', 'İndirim afişi'],
    'Görsel Tasarım': ['Logo güncellemesi', 'Sunum tasarımı'],
    'Sosyal Medya': ['Instagram içerik takvimi', 'LinkedIn paylaşımı'],
    'Etkinlik': ['Kurumsal yemek organizasyonu', 'Eğitim semineri'],
    'Sözleşme İncelemesi': ['Tedarikçi sözleşmesi', 'NDA değerlendirmesi'],
    'Dava Takibi': ['Mevcut dava durumu', 'Yeni dava açılışı'],
    'KVKK': ['Kişisel veri talebi', 'Aydınlatma metni güncellemesi'],
}


MESSAGES = [
    'Detayları aşağıda paylaşıyorum, en kısa sürede dönüş yaparsanız çok memnun olurum.',
    'Bu sorun yaklaşık 2 gündür devam ediyor. Acil çözüm bekliyoruz.',
    'Ekteki dosyada sorunun ekran görüntüsü var. Yardımcı olur musunuz?',
    'İlgili departmana yönlendirebilirseniz çok iyi olur.',
    'Daha önce benzer bir sorunu yaşamıştık, çözüm notlarına bakabilir misiniz?',
    'Konuyla ilgili acil dönüş bekliyoruz; iş akışı tamamen durmuş durumda.',
    'Yeni başladım ve bu konuda nasıl ilerlemem gerektiğini bilmiyorum. Yardım edebilir misiniz?',
]


COMMENTS = [
    'Konuyu inceledim, hemen dönüş yapacağım.',
    'Yöneticime danıştım, onayı geldi.',
    'Ekteki dosyaları kontrol ettim, sorun çözüldü.',
    'Daha fazla bilgi alabilir miyim?',
    'Bu durumu tekrar değerlendirmemiz gerekecek.',
    'Test ettim, sorun devam ediyor.',
    'Teşekkürler, çok yardımcı oldunuz.',
]


# Türkçe gerçek isim ve soyisim havuzları (username = ad.soyad)
MANAGER_NAMES = [
    ('Ahmet', 'Yıldırım'),
    ('Elif', 'Karagöz'),
    ('Mustafa', 'Özdemir'),
    ('Ayşe', 'Çetin'),
    ('Hakan', 'Arslan'),
    ('Fatma', 'Koçak'),
]

AGENT_NAMES = [
    ('Burak', 'Şahin'),
    ('Zeynep', 'Aydın'),
    ('Emre', 'Yılmaz'),
    ('Selin', 'Demir'),
    ('Oğuz', 'Kaya'),
    ('Merve', 'Aksoy'),
    ('Cem', 'Polat'),
    ('Deniz', 'Eren'),
    ('Tolga', 'Çelik'),
    ('Büşra', 'Kurt'),
    ('Murat', 'Doğan'),
    ('İrem', 'Acar'),
]

EMPLOYEE_NAMES = [
    ('Ali', 'Korkmaz'),
    ('Esra', 'Yalçın'),
    ('Serkan', 'Öztürk'),
    ('Gamze', 'Kaplan'),
    ('Onur', 'Güneş'),
    ('Derya', 'Avcı'),
    ('Kadir', 'Çakır'),
    ('Sibel', 'Şen'),
    ('Ufuk', 'Aktaş'),
    ('Neslihan', 'Koç'),
    ('Barış', 'Yıldız'),
    ('Pınar', 'Bozkurt'),
    ('Tuncay', 'Karaca'),
    ('Hülya', 'Türk'),
    ('Volkan', 'Aslan'),
    ('Ceren', 'Uçar'),
    ('Gökhan', 'Bayrak'),
    ('Tuğba', 'Gül'),
    ('Erdem', 'Balcı'),
    ('Melis', 'Duman'),
]


def _to_username(first_name, last_name):
    """Türkçe ad soyaddan küçük harfli username üretir: ad.soyad"""
    tr_map = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
    fn = first_name.lower().translate(tr_map)
    ln = last_name.lower().translate(tr_map)
    return f'{fn}.{ln}'


def _hours_ago(min_h, max_h):
    return timezone.now() - timedelta(hours=random.randint(min_h, max_h))


class Command(BaseCommand):
    help = 'Demo veri yükler (departman, kullanıcı, bilet, etiket vb.).'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Mevcut bilet/bildirim/audit log/etiket verilerini siler')
        parser.add_argument('--tickets', type=int, default=25,
                            help='Oluşturulacak bilet sayısı (varsayılan: 25)')
        parser.add_argument('--users', type=int, default=30,
                            help='Oluşturulacak toplam kullanıcı sayısı (varsayılan: 30)')

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(42)

        if opts['reset']:
            self._reset()

        admin = self._create_admin()
        departments = self._create_departments()
        categories = self._create_categories(departments)
        tags = self._create_tags()
        users = self._create_users(departments, opts['users'])
        tickets = self._create_tickets(users, departments, categories, tags, admin, opts['tickets'])
        self._create_notifications(tickets, users)
        self._create_audit_logs(admin, users, tickets, departments)

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Hazır:\n'
            f'  • {len(departments)} departman, {len(categories)} kategori, {len(tags)} etiket\n'
            f'  • {User.objects.count()} kullanıcı, {len(tickets)} bilet\n'
            f'  • {TicketComment.objects.count()} yorum, {TicketHistory.objects.count()} geçmiş\n'
            f'  • {Notification.objects.count()} bildirim, {AuditLog.objects.count()} audit log\n'
            f'\nGiriş bilgileri: admin/admin123 — diğerleri pass123\n'
        ))

    def _reset(self):
        self.stdout.write('Mevcut demo veriler temizleniyor...')
        Notification.objects.all().delete()
        AuditLog.objects.all().delete()
        TicketComment.objects.all().delete()
        TicketHistory.objects.all().delete()
        Ticket.objects.all().delete()
        Tag.objects.all().delete()
        Category.objects.all().delete()
        Department.objects.all().delete()
        # Süperkullanıcı haricindeki kullanıcıları sil
        User.objects.filter(is_superuser=False).delete()

    def _create_admin(self):
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'first_name': 'Sistem',
                'last_name': 'Yöneticisi',
                'is_staff': True,
                'is_superuser': True,
                'is_active': True,
                'role': Role.ADMIN,
            },
        )
        if created:
            admin.set_password('admin123')
            admin.save()
            self.stdout.write(f'  + admin oluşturuldu (admin/admin123)')
        return admin

    def _create_departments(self):
        depts = []
        for name, desc, _ in DEPARTMENTS:
            d, created = Department.objects.get_or_create(
                name=name, defaults={'description': desc},
            )
            if created:
                self.stdout.write(f'  + departman: {name}')
            depts.append(d)
        return depts

    def _create_categories(self, departments):
        cats = []
        dept_by_name = {d.name: d for d in departments}
        for name, _, cat_names in DEPARTMENTS:
            dept = dept_by_name[name]
            for cn in cat_names:
                c, _ = Category.objects.get_or_create(
                    department=dept, name=cn,
                    defaults={'description': f'{cn} talepleri için.'},
                )
                cats.append(c)
        return cats

    def _create_tags(self):
        tags = []
        for name, color in TAGS:
            t, created = Tag.objects.get_or_create(name=name, defaults={'color': color})
            tags.append(t)
        return tags

    def _create_users(self, departments, total):
        users = []

        # Her departmana 1 manager (Türkçe isimli)
        managers = []
        for i, dept in enumerate(departments):
            first_name, last_name = MANAGER_NAMES[i]
            uname = _to_username(first_name, last_name)
            u, created = User.objects.get_or_create(
                username=uname,
                defaults={
                    'email': f'{uname}@esms.local',
                    'first_name': first_name,
                    'last_name': last_name,
                    'role': Role.MANAGER,
                    'department': dept,
                    'is_active': True,
                    'phone': f'05{random.randint(300000000, 599999999)}',
                },
            )
            if created:
                u.set_password('pass123')
                u.save()
            # Departmana manager ata
            if dept.manager_id != u.pk:
                dept.manager = u
                dept.save(update_fields=['manager'])
            managers.append(u)
            users.append(u)

        # Her departmana 2 agent (Türkçe isimli)
        agents = []
        idx = 0
        for dept in departments:
            for j in range(2):
                first_name, last_name = AGENT_NAMES[idx]
                uname = _to_username(first_name, last_name)
                u, created = User.objects.get_or_create(
                    username=uname,
                    defaults={
                        'email': f'{uname}@esms.local',
                        'first_name': first_name,
                        'last_name': last_name,
                        'role': Role.AGENT,
                        'department': dept,
                        'is_active': True,
                        'phone': f'05{random.randint(300000000, 599999999)}',
                    },
                )
                if created:
                    u.set_password('pass123')
                    u.save()
                agents.append(u)
                users.append(u)
                idx += 1

        # Geri kalan slot employee (Türkçe isimli)
        already = len(users)
        target_employees = max(8, total - already)
        for i in range(target_employees):
            first_name, last_name = EMPLOYEE_NAMES[i % len(EMPLOYEE_NAMES)]
            uname = _to_username(first_name, last_name)
            u, created = User.objects.get_or_create(
                username=uname,
                defaults={
                    'email': f'{uname}@esms.local',
                    'first_name': first_name,
                    'last_name': last_name,
                    'role': Role.EMPLOYEE,
                    'is_active': i > 1,  # ilk 2'si onay bekliyor (pasif)
                    'phone': f'05{random.randint(300000000, 599999999)}',
                    'department': random.choice(departments),
                },
            )
            if created:
                u.set_password('pass123')
                u.save()
            users.append(u)

        self.stdout.write(f'  + {len(users)} kullanıcı (manager/agent/employee, şifre pass123)')
        return users

    def _create_tickets(self, users, departments, categories, tags, admin, count):
        employees = [u for u in users if u.role == Role.EMPLOYEE and u.is_active]
        agents_by_dept = {}
        for u in users:
            if u.role == Role.AGENT and u.department_id:
                agents_by_dept.setdefault(u.department_id, []).append(u)

        tickets = []
        for i in range(count):
            cat = random.choice(categories)
            dept = cat.department
            sender = random.choice(employees) if employees else admin
            priority = random.choice([Priority.LOW, Priority.NORMAL, Priority.NORMAL, Priority.HIGH, Priority.URGENT])
            subject = random.choice(SUBJECT_TEMPLATES.get(cat.name, [cat.name + ' talebi']))
            message = random.choice(MESSAGES)

            t = Ticket.objects.create(
                subject=subject, message=message, status=Status.OPEN,
                priority=priority, sender=sender, department=dept, category=cat,
            )
            # created_at'i geçmişe çek (auto_now_add'i bypass için update)
            ago = _hours_ago(1, 720)  # son 30 gün içinde
            Ticket.objects.filter(pk=t.pk).update(created_at=ago, updated_at=ago)
            t.refresh_from_db()

            # Etiket ata (0-2 adet)
            chosen_tags = random.sample(tags, k=random.randint(0, 2))
            if chosen_tags:
                t.tags.set(chosen_tags)

            TicketHistory.objects.create(ticket=t, actor=sender, action='Bilet oluşturuldu.', created_at=ago)

            # %70 ihtimal üstlen (dept agent'ı)
            dept_agents = agents_by_dept.get(dept.pk, [])
            if dept_agents and random.random() < 0.7:
                agent = random.choice(dept_agents)
                t.assigned_to = agent
                t.status = Status.IN_PROGRESS
                t.save(update_fields=['assigned_to', 'status'])
                take_at = ago + timedelta(hours=random.randint(1, 12))
                TicketHistory.objects.create(
                    ticket=t, actor=agent,
                    action=f'{agent.get_full_name() or agent.username} bileti üstlendi.',
                    created_at=take_at,
                )

                # %60 ihtimal kapat
                if random.random() < 0.6:
                    close_at = take_at + timedelta(hours=random.randint(2, 96))
                    t.status = Status.CLOSED
                    t.closed_at = close_at
                    t.resolution_note = random.choice([
                        'Sorun çözüldü, ekibe bilgi verildi.',
                        'Donanım değiştirildi.',
                        'Kullanıcıya yardımcı olundu.',
                        'İlgili sistem yeniden başlatıldı, sorun giderildi.',
                    ])
                    t.save(update_fields=['status', 'closed_at', 'resolution_note'])
                    TicketHistory.objects.create(
                        ticket=t, actor=agent,
                        action=f'Bilet kapatıldı. Çözüm: {t.resolution_note[:100]}',
                        created_at=close_at,
                    )

                    # %15 ihtimal yeniden açıldı (başarısız olarak işaretlenir)
                    if random.random() < 0.15:
                        reopen_at = close_at + timedelta(hours=random.randint(2, 48))
                        t.status = Status.OPEN
                        t.assigned_to = None
                        t.closed_at = None
                        t.save(update_fields=['status', 'assigned_to', 'closed_at'])
                        TicketHistory.objects.create(
                            ticket=t, actor=sender,
                            action='Bilet yeniden açıldı.', created_at=reopen_at,
                        )

            # %40 ihtimal yorum ekle
            if random.random() < 0.4:
                commenter = random.choice([sender, t.assigned_to or random.choice(dept_agents) if dept_agents else sender])
                if commenter:
                    TicketComment.objects.create(
                        ticket=t, author=commenter,
                        content=random.choice(COMMENTS),
                    )

            tickets.append(t)

        self.stdout.write(f'  + {len(tickets)} bilet oluşturuldu')
        return tickets

    def _create_notifications(self, tickets, users):
        # Atanmış biletlerde sender'a bildirim
        n = 0
        for t in tickets:
            if t.assigned_to and t.sender:
                Notification.objects.create(
                    recipient=t.sender, ticket=t,
                    message=f'Talebiniz "{t.subject}" (#{t.pk}) {t.assigned_to.get_full_name() or t.assigned_to.username} tarafından üstlenildi.',
                    is_read=random.random() < 0.5,
                )
                n += 1
            if t.status == Status.CLOSED and t.sender:
                Notification.objects.create(
                    recipient=t.sender, ticket=t,
                    message=f'Talebiniz "{t.subject}" (#{t.pk}) çözülmüş ve kapatılmıştır.',
                    is_read=random.random() < 0.7,
                )
                n += 1
        # Admin'e onay bekleyen kullanıcı bildirimleri
        admins = [u for u in users if u.role == Role.ADMIN]
        pending = [u for u in users if not u.is_active]
        for adm in admins or [User.objects.filter(is_superuser=True).first()]:
            if not adm:
                continue
            for pu in pending:
                Notification.objects.create(
                    recipient=adm, ticket=None,
                    message=f'Yeni kullanıcı kaydı: "{pu.get_full_name() or pu.username}" (@{pu.username}) onayınızı bekliyor.',
                )
                n += 1
        self.stdout.write(f'  + {n} bildirim')

    def _create_audit_logs(self, admin, users, tickets, departments):
        # Tüm bilet aksiyonları için TicketHistory'den AuditLog türet (kısaltılmış)
        # Auth kayıtları için bazı sahte giriş kayıtları
        n = 0
        for u in random.sample(users, min(15, len(users))):
            AuditLog.objects.create(
                actor=u, category=AuditLog.Category.AUTH,
                action='Giriş başarılı', target_repr=str(u),
                ip_address=f'192.168.1.{random.randint(2, 250)}',
            )
            n += 1
        # Departman oluşturma
        for d in departments:
            AuditLog.objects.create(
                actor=admin, category=AuditLog.Category.DEPARTMENT,
                action=f'Departman oluşturuldu: {d.name}',
                target_repr=d.name, department=d,
            )
            n += 1
        # Bilet oluşturma kayıtları
        for t in random.sample(tickets, min(10, len(tickets))):
            AuditLog.objects.create(
                actor=t.sender, category=AuditLog.Category.TICKET,
                action='Bilet oluşturuldu.', target_repr=str(t),
                ticket=t, department=t.department,
            )
            n += 1
        self.stdout.write(f'  + {n} audit log')
