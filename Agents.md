# Agents.md — Kurumsal Talep Yönetim Sistemi (ESMS)

## Proje Hakkında

Bu proje, kurum içi talep/destek biletlerinin yönetimini sağlayan bir Django web uygulamasıdır. Rol Bazlı Erişim Kontrolü (RBAC), bilet yaşam döngüsü yönetimi, bildirim sistemi ve raporlama özellikleri içerir.

## Teknoloji Yığını

- **Backend:** Python 3 + Django 6.0
- **Veritabanı:** PostgreSQL (`esms_db`)
- **Frontend:** Bootstrap 5 + Bootstrap Icons + Chart.js
- **Kimlik Doğrulama:** Django Auth (AbstractUser genişletilmiş)
- **Sanal Ortam:** `venv/`

## Proje Yapısı

```
enterprise_service_management_system/
├── config/              # Django ayarları ve root URL yapılandırması
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── identity/            # Kullanıcı yönetimi (login, profil, RBAC)
│   ├── models.py        # User modeli + Role enum (EMPLOYEE, AGENT, MANAGER, ADMIN)
│   ├── views.py         # LoginView, ProfileView, profile_update_view
│   ├── admin.py
│   └── urls.py
├── departments/         # Departman ve kategori yönetimi
│   ├── models.py        # Department, Category modelleri
│   ├── views.py         # ListView, CreateView, AJAX categories endpoint
│   ├── admin.py
│   └── urls.py
├── tickets/             # Bilet (talep) yönetimi — ana iş mantığı
│   ├── models.py        # Ticket modeli + Status enum + yaşam döngüsü metodları
│   ├── views.py         # List, Create, Detail, Take, Close, Transfer view'ları
│   ├── validators.py    # Dosya eki validasyonu (uzantı, boyut, içerik)
│   ├── admin.py
│   └── urls.py
├── notifications/       # Bildirim sistemi
│   ├── models.py        # Notification modeli
│   ├── views.py         # ListView, mark_read, mark_all_read
│   ├── context_processors.py  # Navbar bildirim badge sayacı
│   ├── admin.py
│   └── urls.py
├── reports/             # Raporlama ve istatistikler
│   ├── views.py         # ReportDashboardView (Chart.js verileri)
│   └── urls.py
├── dashboard/           # Rol bazlı ana sayfa dashboard'u
│   └── views.py         # DashboardView (EMPLOYEE/AGENT/MANAGER/ADMIN)
├── templates/           # Proje düzeyinde şablonlar
│   ├── base.html        # Ana layout (navbar, mesajlar)
│   ├── dashboard.html   # Rol bazlı ana sayfa
│   └── partials/        # Include edilebilir parçalar
├── static/
│   └── css/style.css    # Minimal özel stiller
├── requirements.txt
└── manage.py
```

## Kullanıcı Rolleri (RBAC)

| Rol | Açıklama | Yetkileri |
|-----|----------|-----------|
| `EMPLOYEE` | Çalışan | Bilet oluşturma, kendi biletlerini görme |
| `AGENT` | Personel | Departman biletlerini görme, üstlenme, kapatma, transfer |
| `MANAGER` | Yönetici | Agent yetkilerine ek olarak personel iş yükü takibi |
| `ADMIN` | Admin | Tüm sisteme erişim, tüm biletleri yönetme |

## Bilet Yaşam Döngüsü

```
OPEN → (üstlen) → IN_PROGRESS → (kapat) → CLOSED
  ↑                    |
  └── (transfer) ──────┘
```

- **OPEN:** Bilet oluşturuldu, henüz üstlenilmedi
- **IN_PROGRESS:** Personel bileti üstlendi, çözüm sürecinde
- **CLOSED:** Bilet çözüldü ve kapatıldı
- **Transfer:** Bilet başka departmana aktarıldığında OPEN'a döner

## Geliştirme Komutları

```bash
# Sanal ortamı aktifleştir
source venv/bin/activate  # veya: . venv/bin/activate.fish

# Migration oluştur ve uygula
python manage.py makemigrations
python manage.py migrate

# Süper kullanıcı oluştur
python manage.py createsuperuser

# Geliştirme sunucusunu başlat
python manage.py runserver

# Sistem kontrolü
python manage.py check
```

## Dosya Eki Validasyonu

- **İzin verilen türler:** PDF, PNG, JPG, JPEG, DOCX
- **Maksimum boyut:** 10 MB
- **Güvenlik:** Magic bytes ile dosya içeriği doğrulaması

## Önemli URL'ler

| URL | Açıklama |
|-----|----------|
| `/` | Ana sayfa (rol bazlı dashboard) |
| `/admin/` | Django admin paneli |
| `/identity/login/` | Giriş sayfası |
| `/identity/profile/` | Kullanıcı profili |
| `/tickets/` | Bilet listesi |
| `/tickets/create/` | Yeni bilet oluşturma |
| `/tickets/<id>/` | Bilet detayı |
| `/tickets/<id>/transfer/` | Bilet transferi |
| `/departments/` | Departman listesi |
| `/departments/<id>/categories/` | AJAX kategori endpoint |
| `/notifications/` | Bildirimler |
| `/reports/` | Raporlar ve istatistikler |

## Kod Standartları

- Docstring yerine `#` ile inline yorum satırları kullanılır
- `on_delete` stratejileri satır sonunda `#` ile açıklanır
- `Meta` ve `__str__` metodları her modelde standart yorum ile belgelenir
- Bootstrap 5 utility class'ları tercih edilir, özel CSS minimal tutulur
