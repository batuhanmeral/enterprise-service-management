"""Demo veri yükleme komutu.

Kullanım:
    python manage.py seed_demo                    # mevcut verileri korur, ekler
    python manage.py seed_demo --reset            # önceki demo verileri temizleyip yeniden oluşturur
    python manage.py seed_demo --tickets 400      # bilet sayısını özelleştir (default 250)
    python manage.py seed_demo --users 60         # toplam çalışan/personel sayısını özelleştir
    python manage.py seed_demo --days 120         # bilet tarih aralığı (geçmiş gün sayısı, default 90)

Oluşturulanlar (defaults):
- 1 süperkullanıcı (admin / admin123)
- 6 departman + 28 kategori + 10 etiket
- 60 kullanıcı (1 admin, 6 manager, 18 agent, ~35 employee) — şifre: pass123
- 250 bilet (gerçekçi yaşam döngüsü dağılımı: OPEN/IN_PROGRESS/RESOLVED/CLOSED/ESCALATED)
- CSAT puanları, reopen geçmişi, eskalasyon, SLA ihlalleri (organik dağılım)
- Bildirimler ve audit log kayıtları
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from departments.models import Department, Category
from tickets.models import (
    Ticket, Status, Priority, Tag, TicketComment, TicketHistory,
    TicketActionType, SLA_HOURS,
)
from notifications.models import Notification
from identity.models import Role, AuditLog


User = get_user_model()


DEPARTMENTS = [
    ('Bilgi İşlem', 'Donanım, yazılım, ağ ve sistem destek talepleri.', [
        'Donanım Arızası', 'Yazılım Kurulum', 'Ağ Sorunu', 'E-posta',
        'VPN Erişim', 'Yazıcı', 'Veritabanı', 'Güvenlik İhlali',
    ]),
    ('İnsan Kaynakları', 'İzin, bordro ve özlük işlemleri.', [
        'İzin Talebi', 'Bordro', 'Özlük Belgeleri', 'İşe Alım', 'Eğitim',
        'Performans Değerlendirme',
    ]),
    ('Muhasebe', 'Fatura, ödeme ve mali raporlar.', [
        'Fatura Sorgu', 'Ödeme Takibi', 'Vergi', 'Masraf Beyanı', 'Mutabakat',
    ]),
    ('İdari İşler', 'Ofis, lojistik ve genel idari talepler.', [
        'Ofis Malzemesi', 'Temizlik', 'Ulaşım', 'Yemekhane', 'Güvenlik',
    ]),
    ('Pazarlama', 'Kampanya, reklam ve içerik talepleri.', [
        'Kampanya Talebi', 'Görsel Tasarım', 'Sosyal Medya', 'Etkinlik',
    ]),
    ('Hukuk', 'Sözleşme, dava ve hukuki danışmanlık.', [
        'Sözleşme İncelemesi', 'Dava Takibi', 'KVKK',
    ]),
]


TAGS = [
    ('Donanım', '#198754'), ('Yazılım', '#0dcaf0'), ('Ağ / İnternet', '#0d6efd'),
    ('Erişim Talebi', '#6f42c1'), ('İç Talep', '#20c997'), ('Tekrar Eden', '#fd7e14'),
    ('Eğitim', '#e83e8c'), ('Müşteri', '#6c757d'), ('Güvenlik', '#dc3545'),
    ('Raporlama', '#ffc107'),
]


SUBJECT_TEMPLATES = {
    'Donanım Arızası': ['Bilgisayar açılmıyor', 'Klavye tuşları çalışmıyor', 'Monitör titreme yapıyor', 'Mouse tepki vermiyor', 'Disk sesli çalışıyor'],
    'Yazılım Kurulum': ['Office kurulumu gerekli', 'AutoCAD lisans aktivasyonu', 'Adobe paketleri yüklenecek', 'IDE kurulumu'],
    'Ağ Sorunu': ['İnternet bağlantısı kopuyor', 'WiFi sinyali zayıf', 'Sunucuya erişemiyorum', 'DNS çözümlenmiyor'],
    'E-posta': ['Outlook açılmıyor', 'E-postalar gelmiyor', 'Spam filtresi sorunlu', 'Mail kotası doldu'],
    'VPN Erişim': ['VPN bağlantısı kurulmuyor', 'VPN sertifikası süresi dolmuş', 'Yeni VPN kullanıcısı'],
    'Yazıcı': ['Yazıcı kağıt sıkıştırıyor', 'Toner bitti', 'Yazıcı ağda görünmüyor', 'Yazdırma kuyruğu takıldı'],
    'Veritabanı': ['Sorgu çok yavaş', 'Bağlantı zaman aşımına uğruyor', 'Yedek alınamadı'],
    'Güvenlik İhlali': ['Şüpheli e-posta aldım', 'Hesabım kilitlendi', 'Phishing girişimi'],
    'İzin Talebi': ['Yıllık izin talebi', 'Mazeret izni', 'Doğum izni hakkında', 'Ücretsiz izin'],
    'Bordro': ['Maaş bordrom hatalı', 'Geçen ayın bordrosunu alamadım', 'AGI hesaplaması'],
    'Özlük Belgeleri': ['İşveren yazısı talep ediyorum', 'Hizmet belgesi', 'SGK hizmet dökümü'],
    'İşe Alım': ['Açık pozisyon hakkında bilgi', 'CV gönderim', 'Mülakat planlaması'],
    'Eğitim': ['Online eğitim talebi', 'Sertifika programı', 'Yabancı dil kursu'],
    'Performans Değerlendirme': ['Yıl sonu değerlendirme', 'Hedef revizyonu'],
    'Fatura Sorgu': ['Geçen ayın faturası gelmedi', 'Faturada hata var', 'Fatura iadesi'],
    'Ödeme Takibi': ['Ödememiz görünmüyor', 'Mutabakat', 'Avans talebi'],
    'Vergi': ['KDV beyannamesi', 'Stopaj kesintisi', 'Damga vergisi'],
    'Masraf Beyanı': ['Yol masrafı', 'Yemek fişi onayı', 'Konaklama gideri'],
    'Mutabakat': ['Cari mutabakat farkı', 'Yıl sonu mutabakatı'],
    'Ofis Malzemesi': ['Kalem, defter siparişi', 'Yeni masa talebi', 'Sandalye değişimi'],
    'Temizlik': ['Tuvaletler kirli', 'Camların temizlenmesi', 'Halı yıkama'],
    'Ulaşım': ['Servis güzergahı değişikliği', 'Otopark talebi', 'Taksi onayı'],
    'Yemekhane': ['Menü talebi', 'Vejetaryen seçenek', 'Glutensiz menü'],
    'Güvenlik': ['Kart çalışmıyor', 'Yeni misafir kartı', 'Kapı arızası'],
    'Kampanya Talebi': ['Yıl sonu kampanyası planı', 'İndirim afişi', 'Yaz kampanyası'],
    'Görsel Tasarım': ['Logo güncellemesi', 'Sunum tasarımı', 'Banner tasarımı'],
    'Sosyal Medya': ['Instagram içerik takvimi', 'LinkedIn paylaşımı', 'YouTube planı'],
    'Etkinlik': ['Kurumsal yemek organizasyonu', 'Eğitim semineri', 'Lansman etkinliği'],
    'Sözleşme İncelemesi': ['Tedarikçi sözleşmesi', 'NDA değerlendirmesi', 'Bayilik sözleşmesi'],
    'Dava Takibi': ['Mevcut dava durumu', 'Yeni dava açılışı', 'Temyiz süreci'],
    'KVKK': ['Kişisel veri talebi', 'Aydınlatma metni güncellemesi', 'Veri silme talebi'],
}


MESSAGES = [
    'Detayları aşağıda paylaşıyorum, en kısa sürede dönüş yaparsanız çok memnun olurum.',
    'Bu sorun yaklaşık 2 gündür devam ediyor. Acil çözüm bekliyoruz.',
    'Ekteki dosyada sorunun ekran görüntüsü var. Yardımcı olur musunuz?',
    'İlgili departmana yönlendirebilirseniz çok iyi olur.',
    'Daha önce benzer bir sorunu yaşamıştık, çözüm notlarına bakabilir misiniz?',
    'Konuyla ilgili acil dönüş bekliyoruz; iş akışı tamamen durmuş durumda.',
    'Yeni başladım ve bu konuda nasıl ilerlemem gerektiğini bilmiyorum. Yardım edebilir misiniz?',
    'Ekiple birlikte birkaç farklı yaklaşım denedik ama sonuç alamadık.',
    'Süreç ile ilgili dokümantasyonu da paylaşabilirseniz harika olur.',
]


COMMENTS = [
    'Konuyu inceledim, hemen dönüş yapacağım.',
    'Yöneticime danıştım, onayı geldi.',
    'Ekteki dosyaları kontrol ettim, sorun çözüldü.',
    'Daha fazla bilgi alabilir miyim?',
    'Bu durumu tekrar değerlendirmemiz gerekecek.',
    'Test ettim, sorun devam ediyor.',
    'Teşekkürler, çok yardımcı oldunuz.',
    'Departman yöneticisine ilettim, yarın geri dönüş yapacağım.',
    'Tedarikçi ile iletişime geçtim, 24 saat içinde yanıt bekliyoruz.',
]


RESOLUTION_NOTES = [
    'Sorun tespit edildi ve giderildi. Sistem yeniden başlatıldı.',
    'İlgili sertifika güncellendi, erişim sağlandı.',
    'Donanım değişimi yapıldı, test edildi.',
    'Kullanıcıya gerekli yetkiler tanımlandı.',
    'Yazılım güncellemesi uygulandı, sorun çözüldü.',
    'Mutabakat tamamlandı, kayıtlar güncellendi.',
    'Belge hazırlandı ve teslim edildi.',
    'Talep onaylandı, ilgili süreç başlatıldı.',
    'Konu KVKK uyumluluğu çerçevesinde değerlendirildi.',
    'Saha ekibi tarafından yerinde müdahale edildi.',
]


REJECTION_REASONS = [
    'Sorun hâlâ devam ediyor, lütfen tekrar inceleyin.',
    'Önerilen çözüm ihtiyacımı karşılamıyor.',
    'Aynı hata mesajı yine alınıyor.',
    'İşlem yarım kalmış görünüyor, eksik bir şey var.',
    'Test ettim ama sonuç değişmedi.',
    'Çözüm açıklaması yetersiz, daha fazla detay gerekli.',
]


# Türkçe gerçek isim havuzları (username = ad.soyad)
MANAGER_NAMES = [
    ('Ahmet', 'Yıldırım'), ('Elif', 'Karagöz'), ('Mustafa', 'Özdemir'),
    ('Ayşe', 'Çetin'), ('Hakan', 'Arslan'), ('Fatma', 'Koçak'),
]

AGENT_NAMES = [
    ('Burak', 'Şahin'), ('Zeynep', 'Aydın'), ('Emre', 'Yılmaz'),
    ('Selin', 'Demir'), ('Oğuz', 'Kaya'), ('Merve', 'Aksoy'),
    ('Cem', 'Polat'), ('Deniz', 'Eren'), ('Tolga', 'Çelik'),
    ('Büşra', 'Kurt'), ('Murat', 'Doğan'), ('İrem', 'Acar'),
    ('Sinan', 'Erdoğan'), ('Pelin', 'Tunç'), ('Hasan', 'Güler'),
    ('Yasemin', 'Korkut'), ('Berk', 'Çiftçi'), ('Nazlı', 'Sezer',),
]

EMPLOYEE_NAMES = [
    ('Ali', 'Korkmaz'), ('Esra', 'Yalçın'), ('Serkan', 'Öztürk'),
    ('Gamze', 'Kaplan'), ('Onur', 'Güneş'), ('Derya', 'Avcı'),
    ('Kadir', 'Çakır'), ('Sibel', 'Şen'), ('Ufuk', 'Aktaş'),
    ('Neslihan', 'Koç'), ('Barış', 'Yıldız'), ('Pınar', 'Bozkurt'),
    ('Tuncay', 'Karaca'), ('Hülya', 'Türk'), ('Volkan', 'Aslan'),
    ('Ceren', 'Uçar'), ('Gökhan', 'Bayrak'), ('Tuğba', 'Gül'),
    ('Erdem', 'Balcı'), ('Melis', 'Duman'), ('Kerem', 'Sarı'),
    ('Aslı', 'Yavuz'), ('Berkay', 'Topal'), ('Funda', 'Erkan'),
    ('Caner', 'Tekin'), ('Şule', 'Erdem'), ('Levent', 'Akkaya'),
    ('Yıldız', 'Pekcan'), ('Mert', 'Toprak'), ('Cansu', 'Bilgin'),
    ('Burhan', 'Karadağ'), ('Damla', 'Yener'), ('Sezer', 'Çoban'),
    ('Tülay', 'Erol'), ('Furkan', 'Aybar'),
]


def _to_username(first_name, last_name):
    """Türkçe ad soyaddan küçük harfli username üretir: ad.soyad"""
    tr_map = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
    fn = first_name.lower().translate(tr_map)
    ln = last_name.lower().translate(tr_map)
    return f'{fn}.{ln}'


# Önceliğe göre çözüm süresi aralığı (saat) — bazı ihlaller organik şekilde oluşur
def _resolution_hours_for(priority):
    sla = SLA_HOURS.get(priority, 72)
    # %75 SLA içinde, %25 dışında
    if random.random() < 0.75:
        return random.uniform(0.5, sla * 0.95)
    return random.uniform(sla * 1.05, sla * 2.5)


def _csat_rating():
    """4-5'e ağırlıklı, 1-2'ye nadir CSAT puanı."""
    return random.choices([1, 2, 3, 4, 5], weights=[3, 5, 12, 35, 45], k=1)[0]


def _set_history_ts(history, ts):
    """auto_now_add'i bypass ederek TicketHistory.created_at'i geçmişe çeker."""
    TicketHistory.objects.filter(pk=history.pk).update(created_at=ts)


def _set_ticket_created(ticket, ts):
    """auto_now_add'i bypass ederek Ticket.created_at/updated_at'i geçmişe çeker."""
    Ticket.objects.filter(pk=ticket.pk).update(created_at=ts, updated_at=ts)


class Command(BaseCommand):
    help = 'Demo veri yükler (departman, kullanıcı, bilet, etiket, CSAT, reopen, eskalasyon).'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Mevcut bilet/bildirim/audit log/etiket verilerini siler')
        parser.add_argument('--tickets', type=int, default=250,
                            help='Oluşturulacak bilet sayısı (varsayılan: 250)')
        parser.add_argument('--users', type=int, default=60,
                            help='Oluşturulacak toplam kullanıcı sayısı (varsayılan: 60)')
        parser.add_argument('--days', type=int, default=90,
                            help='Biletlerin yayılacağı geçmiş gün aralığı (varsayılan: 90)')

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
        tickets = self._create_tickets(
            users, departments, categories, tags, admin,
            opts['tickets'], opts['days'],
        )
        self._create_notifications(tickets, users)
        self._create_audit_logs(admin, users, tickets, departments)

        # Özet
        from collections import Counter
        status_counter = Counter(t.status for t in tickets)
        csat_count = sum(1 for t in tickets if t.csat_rating)
        reopened = sum(1 for t in tickets if t.reopen_count > 0)
        escalated = status_counter.get(Status.ESCALATED, 0)

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Hazır:\n'
            f'  • {len(departments)} departman, {len(categories)} kategori, {len(tags)} etiket\n'
            f'  • {User.objects.count()} kullanıcı, {len(tickets)} bilet\n'
            f'    └─ OPEN: {status_counter.get(Status.OPEN, 0)}, '
            f'IN_PROGRESS: {status_counter.get(Status.IN_PROGRESS, 0)}, '
            f'RESOLVED: {status_counter.get(Status.RESOLVED, 0)}, '
            f'CLOSED: {status_counter.get(Status.CLOSED, 0)}, '
            f'ESCALATED: {escalated}\n'
            f'    └─ {csat_count} CSAT puanı, {reopened} yeniden açılmış bilet\n'
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
            self.stdout.write('  + admin oluşturuldu (admin/admin123)')
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
            t, _ = Tag.objects.get_or_create(name=name, defaults={'color': color})
            tags.append(t)
        return tags

    def _create_users(self, departments, total):
        users = []

        # Her departmana 1 manager
        for i, dept in enumerate(departments):
            first_name, last_name = MANAGER_NAMES[i % len(MANAGER_NAMES)]
            uname = _to_username(first_name, last_name)
            u, created = User.objects.get_or_create(
                username=uname,
                defaults={
                    'email': f'{uname}@dispatch.local',
                    'first_name': first_name, 'last_name': last_name,
                    'role': Role.MANAGER, 'department': dept, 'is_active': True,
                    'phone': f'05{random.randint(300000000, 599999999)}',
                },
            )
            if created:
                u.set_password('pass123')
                u.save()
            # Departman yöneticisi: User.role=MANAGER + User.department=dept ile türetilir,
            # ayrıca FK güncellemesi gerekmez.
            users.append(u)

        # Her departmana 3 agent
        idx = 0
        for dept in departments:
            for _ in range(3):
                first_name, last_name = AGENT_NAMES[idx % len(AGENT_NAMES)]
                uname = _to_username(first_name, last_name)
                u, created = User.objects.get_or_create(
                    username=uname,
                    defaults={
                        'email': f'{uname}@dispatch.local',
                        'first_name': first_name, 'last_name': last_name,
                        'role': Role.AGENT, 'department': dept, 'is_active': True,
                        'phone': f'05{random.randint(300000000, 599999999)}',
                    },
                )
                if created:
                    u.set_password('pass123')
                    u.save()
                users.append(u)
                idx += 1

        # Geri kalan slot employee
        already = len(users)
        target_employees = max(15, total - already)
        for i in range(target_employees):
            first_name, last_name = EMPLOYEE_NAMES[i % len(EMPLOYEE_NAMES)]
            uname = _to_username(first_name, last_name)
            u, created = User.objects.get_or_create(
                username=uname,
                defaults={
                    'email': f'{uname}@dispatch.local',
                    'first_name': first_name, 'last_name': last_name,
                    'role': Role.EMPLOYEE,
                    'is_active': i > 1,  # ilk 2'si pasif (admin onayı bekliyor)
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

    def _create_tickets(self, users, departments, categories, tags, admin, count, days_back):
        employees = [u for u in users if u.role == Role.EMPLOYEE and u.is_active]
        agents_by_dept = {}
        for u in users:
            if u.role == Role.AGENT and u.department_id:
                agents_by_dept.setdefault(u.department_id, []).append(u)

        # Yaşam döngüsü dağılımı (toplamı 100):
        #   OPEN: 12, IN_PROGRESS: 18, RESOLVED: 15, CLOSED: 50, ESCALATED: 5
        statuses_pool = (
            [Status.OPEN] * 12 +
            [Status.IN_PROGRESS] * 18 +
            [Status.RESOLVED] * 15 +
            [Status.CLOSED] * 50 +
            [Status.ESCALATED] * 5
        )

        priorities_pool = [Priority.LOW, Priority.NORMAL, Priority.NORMAL, Priority.NORMAL, Priority.HIGH, Priority.URGENT]

        tickets = []
        for i in range(count):
            cat = random.choice(categories)
            dept = cat.department
            sender = random.choice(employees) if employees else admin
            priority = random.choice(priorities_pool)
            target_status = random.choice(statuses_pool)
            subject = random.choice(SUBJECT_TEMPLATES.get(cat.name, [f'{cat.name} talebi']))
            message = random.choice(MESSAGES)

            # created_at: son `days_back` gün içinde rastgele dağıt
            created_at = timezone.now() - timedelta(
                hours=random.randint(2, days_back * 24)
            )

            t = Ticket.objects.create(
                subject=subject, message=message, status=Status.OPEN,
                priority=priority, sender=sender, department=dept, category=cat,
            )
            _set_ticket_created(t, created_at)
            t.refresh_from_db()

            # Etiket (0-3 adet)
            chosen_tags = random.sample(tags, k=random.randint(0, 3))
            if chosen_tags:
                t.tags.set(chosen_tags)

            h = TicketHistory.objects.create(
                ticket=t, actor=sender,
                action='Bilet oluşturuldu.',
                action_type=TicketActionType.CREATED,
            )
            _set_history_ts(h, created_at)

            dept_agents = agents_by_dept.get(dept.pk, [])
            agent = random.choice(dept_agents) if dept_agents else None

            # OPEN: hiçbir şey yapma
            if target_status == Status.OPEN or agent is None:
                tickets.append(t)
                continue

            # Üstlen → IN_PROGRESS
            take_at = created_at + timedelta(hours=random.randint(1, 12))
            t.assigned_to = agent
            t.status = Status.IN_PROGRESS
            t.save(update_fields=['assigned_to', 'status'])
            h = TicketHistory.objects.create(
                ticket=t, actor=agent,
                action=f'{agent.get_full_name() or agent.username} bileti üstlendi.',
                action_type=TicketActionType.TAKEN,
            )
            _set_history_ts(h, take_at)

            if target_status == Status.IN_PROGRESS:
                # Bazı IN_PROGRESS biletlerinde yorum bırak
                self._maybe_add_comment(t, sender, agent, take_at)
                tickets.append(t)
                continue

            # Çöz → RESOLVED
            resolved_at = take_at + timedelta(hours=_resolution_hours_for(priority))
            resolution_note = random.choice(RESOLUTION_NOTES)
            t.status = Status.RESOLVED
            t.resolved_at = resolved_at
            t.resolution_note = resolution_note
            t.save(update_fields=['status', 'resolved_at', 'resolution_note'])
            h = TicketHistory.objects.create(
                ticket=t, actor=agent,
                action=f'Bilet çözüldü olarak işaretlendi: {resolution_note[:100]}',
                action_type=TicketActionType.RESOLVED,
            )
            _set_history_ts(h, resolved_at)

            if target_status == Status.RESOLVED:
                self._maybe_add_comment(t, sender, agent, resolved_at)
                tickets.append(t)
                continue

            # Burada CLOSED veya ESCALATED akışı
            if target_status == Status.ESCALATED:
                # 3 kez RED → ESCALATED. İlk RESOLVED zaten yapıldı, 2 kez daha tekrarla, 3. RED'de eskale et.
                cur_at = resolved_at
                for cycle in range(2):
                    reject_at = cur_at + timedelta(hours=random.randint(2, 36))
                    reason = random.choice(REJECTION_REASONS)
                    t.reopen_count = cycle + 1
                    t.rejection_reason = reason
                    t.status = Status.IN_PROGRESS
                    t.resolved_at = None
                    t.save(update_fields=['reopen_count', 'rejection_reason', 'status', 'resolved_at'])
                    h = TicketHistory.objects.create(
                        ticket=t, actor=sender,
                        action=f'Çözüm reddedildi: {reason}',
                        action_type=TicketActionType.RESOLUTION_REJECTED,
                    )
                    _set_history_ts(h, reject_at)

                    re_resolved_at = reject_at + timedelta(hours=_resolution_hours_for(priority))
                    t.status = Status.RESOLVED
                    t.resolved_at = re_resolved_at
                    t.resolution_note = random.choice(RESOLUTION_NOTES)
                    t.save(update_fields=['status', 'resolved_at', 'resolution_note'])
                    h = TicketHistory.objects.create(
                        ticket=t, actor=agent,
                        action=f'Yeniden çözüldü olarak işaretlendi: {t.resolution_note[:100]}',
                        action_type=TicketActionType.RESOLVED,
                    )
                    _set_history_ts(h, re_resolved_at)
                    cur_at = re_resolved_at

                # 3. RED → ESCALATED
                escalate_at = cur_at + timedelta(hours=random.randint(2, 24))
                final_reason = random.choice(REJECTION_REASONS)
                t.status = Status.ESCALATED
                t.escalated_at = escalate_at
                t.rejection_reason = final_reason
                t.save(update_fields=['status', 'escalated_at', 'rejection_reason'])
                h = TicketHistory.objects.create(
                    ticket=t, actor=sender,
                    action=f'3. kez reddedildi, eskalasyona alındı: {final_reason}',
                    action_type=TicketActionType.ESCALATED,
                )
                _set_history_ts(h, escalate_at)

                self._maybe_add_comment(t, sender, agent, escalate_at)
                tickets.append(t)
                continue

            # CLOSED akışı:
            # - %15 ihtimal: 1-2 reddetme döngüsü, sonra onay
            # - %85 ihtimal: doğrudan onay (veya AUTO_CLOSE)
            cur_at = resolved_at
            if random.random() < 0.15:
                num_rejects = random.choice([1, 2])
                for cycle in range(num_rejects):
                    reject_at = cur_at + timedelta(hours=random.randint(2, 48))
                    reason = random.choice(REJECTION_REASONS)
                    t.reopen_count = cycle + 1
                    t.rejection_reason = reason
                    t.status = Status.IN_PROGRESS
                    t.resolved_at = None
                    t.save(update_fields=['reopen_count', 'rejection_reason', 'status', 'resolved_at'])
                    h = TicketHistory.objects.create(
                        ticket=t, actor=sender,
                        action=f'Çözüm reddedildi: {reason}',
                        action_type=TicketActionType.RESOLUTION_REJECTED,
                    )
                    _set_history_ts(h, reject_at)

                    re_resolved_at = reject_at + timedelta(hours=_resolution_hours_for(priority))
                    t.status = Status.RESOLVED
                    t.resolved_at = re_resolved_at
                    t.resolution_note = random.choice(RESOLUTION_NOTES)
                    t.save(update_fields=['status', 'resolved_at', 'resolution_note'])
                    h = TicketHistory.objects.create(
                        ticket=t, actor=agent,
                        action=f'Yeniden çözüldü olarak işaretlendi: {t.resolution_note[:100]}',
                        action_type=TicketActionType.RESOLVED,
                    )
                    _set_history_ts(h, re_resolved_at)
                    cur_at = re_resolved_at

            # Onay → CLOSED (manuel veya AUTO_CLOSE)
            confirm_at = cur_at + timedelta(hours=random.randint(2, 96))
            auto_closed = random.random() < 0.20
            t.status = Status.CLOSED
            t.closed_at = confirm_at
            t.save(update_fields=['status', 'closed_at'])
            if auto_closed:
                h = TicketHistory.objects.create(
                    ticket=t, actor=None,
                    action='Bilet 3 gün içinde onaylanmadığı için otomatik kapatıldı.',
                    action_type=TicketActionType.AUTO_CLOSED,
                )
            else:
                h = TicketHistory.objects.create(
                    ticket=t, actor=sender,
                    action='Çözüm onaylandı, bilet kapatıldı.',
                    action_type=TicketActionType.RESOLUTION_CONFIRMED,
                )
            _set_history_ts(h, confirm_at)

            # CSAT (kapanan biletlerin %75'inde, otomatik kapananların %30'unda)
            csat_chance = 0.30 if auto_closed else 0.75
            if random.random() < csat_chance:
                rating = _csat_rating()
                t.csat_rating = rating
                t.save(update_fields=['csat_rating'])
                h = TicketHistory.objects.create(
                    ticket=t, actor=sender,
                    action=f'Memnuniyet puanı: {rating}/5',
                    action_type=TicketActionType.CSAT_RATED,
                )
                _set_history_ts(h, confirm_at + timedelta(hours=random.randint(1, 24)))

            self._maybe_add_comment(t, sender, agent, confirm_at)
            tickets.append(t)

        self.stdout.write(f'  + {len(tickets)} bilet (gerçekçi yaşam döngüsü dağılımı)')
        return tickets

    def _maybe_add_comment(self, ticket, sender, agent, after_ts):
        """Bilet yaşam döngüsünün herhangi bir noktasında 0-2 yorum ekler."""
        n = random.choices([0, 1, 2], weights=[40, 40, 20], k=1)[0]
        for _ in range(n):
            commenter = random.choice([sender, agent]) if agent else sender
            if not commenter:
                continue
            c = TicketComment.objects.create(
                ticket=ticket, author=commenter,
                content=random.choice(COMMENTS),
            )
            # Yorum zamanını biletin ilgili zamanına yakın çek
            offset = timedelta(hours=random.randint(1, 48))
            TicketComment.objects.filter(pk=c.pk).update(created_at=after_ts + offset)

    def _create_notifications(self, tickets, users):
        n = 0
        for t in tickets:
            if t.assigned_to and t.sender:
                Notification.objects.create(
                    recipient=t.sender, ticket=t,
                    message=f'Talebiniz "{t.subject}" (#{t.pk}) {t.assigned_to.get_full_name() or t.assigned_to.username} tarafından üstlenildi.',
                    is_read=random.random() < 0.5,
                )
                n += 1
            if t.status == Status.RESOLVED and t.sender:
                Notification.objects.create(
                    recipient=t.sender, ticket=t,
                    message=f'Talebiniz "{t.subject}" (#{t.pk}) çözüldü olarak işaretlendi. Onayınız bekleniyor.',
                    is_read=random.random() < 0.3,
                )
                n += 1
            elif t.status == Status.CLOSED and t.sender:
                Notification.objects.create(
                    recipient=t.sender, ticket=t,
                    message=f'Talebiniz "{t.subject}" (#{t.pk}) kapatıldı.',
                    is_read=random.random() < 0.7,
                )
                n += 1
            elif t.status == Status.ESCALATED:
                # Departman yöneticilerine bildir (multi-manager)
                if t.department:
                    for mgr in t.department.managers:
                        Notification.objects.create(
                            recipient=mgr, ticket=t,
                            message=f'Bilet "{t.subject}" (#{t.pk}) eskalasyona alındı, müdahale gerekli.',
                            is_read=False,
                        )
                        n += 1

        # Pasif kullanıcı bildirimleri admin'e
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
        n = 0
        for u in random.sample(users, min(25, len(users))):
            AuditLog.objects.create(
                actor=u, category=AuditLog.Category.AUTH,
                action='Giriş başarılı', target_repr=str(u),
                ip_address=f'192.168.1.{random.randint(2, 250)}',
            )
            n += 1
        for d in departments:
            AuditLog.objects.create(
                actor=admin, category=AuditLog.Category.DEPARTMENT,
                action=f'Departman oluşturuldu: {d.name}',
                target_repr=d.name, department=d,
            )
            n += 1
        for t in random.sample(tickets, min(20, len(tickets))):
            AuditLog.objects.create(
                actor=t.sender, category=AuditLog.Category.TICKET,
                action='Bilet oluşturuldu.', target_repr=str(t),
                ticket=t, department=t.department,
            )
            n += 1
        self.stdout.write(f'  + {n} audit log')
