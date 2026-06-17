# Demo Data (seed_demo)

Bu dosya, `seed_demo` komutunun olusturdugu demo verileri ozetler. Komut dosyasi
`.docs/commands/seed_demo.py` altinda tutulur; `manage.py seed_demo` ile calistirmak icin
kurulu bir app'in `management/commands/` klasorune (or. `identity/management/commands/`) konmalidir.
Yasam dongusu durumlari (OPEN / IN_PROGRESS / RESOLVED / CLOSED / ESCALATED), CSAT, reopen
sayaci ve SLA metriklerini doldurmak icin yeterince zengin veri uretir.
Not: Asil degerler Turkce karakterler icerir; bu dokumanda ASCII transliterasyon kullanildi.

## Komut Kullanimi
- `python manage.py seed_demo` (default 250 bilet, 60 kullanici, 90 gun)
- `python manage.py seed_demo --reset` (mevcut bilet/bildirim/audit/etiket veriyi siler)
- `python manage.py seed_demo --tickets 400`
- `python manage.py seed_demo --users 80`
- `python manage.py seed_demo --days 120` (created_at araligi)

## Giris Bilgileri
- Admin: `admin / admin123`
- Diger kullanicilar (manager / agent / employee): `pass123`

## Departmanlar ve Kategoriler (6 departman, 31 kategori)
- Bilgi Islem
  - Donanim Arizasi, Yazilim Kurulum, Ag Sorunu, E-posta, VPN Erisim, Yazici, Veritabani, Guvenlik Ihlali
- Insan Kaynaklari
  - Izin Talebi, Bordro, Ozluk Belgeleri, Ise Alim, Egitim, Performans Degerlendirme
- Muhasebe
  - Fatura Sorgu, Odeme Takibi, Vergi, Masraf Beyani, Mutabakat
- Idari Isler
  - Ofis Malzemesi, Temizlik, Ulasim, Yemekhane, Guvenlik
- Pazarlama
  - Kampanya Talebi, Gorsel Tasarim, Sosyal Medya, Etkinlik
- Hukuk
  - Sozlesme Incelemesi, Dava Takibi, KVKK

## Etiketler (isim, renk)
- Donanim, #198754
- Yazilim, #0dcaf0
- Ag / Internet, #0d6efd
- Erisim Talebi, #6f42c1
- Ic Talep, #20c997
- Tekrar Eden, #fd7e14
- Egitim, #e83e8c
- Musteri, #6c757d
- Guvenlik, #dc3545
- Raporlama, #ffc107

## Kullanicilar (varsayilan: 60)
- 1 admin (super user)
- 6 manager (her departmana 1)
- 18 agent (her departmana 3)
- ~35 employee (rastgele departmana atanmis)
- Employee grubunun ilk 2 hesabi pasif (admin onayi bekliyor)
- Multi-manager mimarisi: yeni departman yonetici FK'si yok; rol+departman uzerinden turetilir.

### Sabit Kullanici Listesi (admin + manager + agent — 25 hesap)

| Nickname | Rol | Departman |
| --- | --- | --- |
| admin | ADMIN | - |
| ahmet.yildirim | MANAGER | Bilgi Islem |
| elif.karagoz | MANAGER | Insan Kaynaklari |
| mustafa.ozdemir | MANAGER | Muhasebe |
| ayse.cetin | MANAGER | Idari Isler |
| hakan.arslan | MANAGER | Pazarlama |
| fatma.kocak | MANAGER | Hukuk |
| burak.sahin | AGENT | Bilgi Islem |
| zeynep.aydin | AGENT | Bilgi Islem |
| emre.yilmaz | AGENT | Bilgi Islem |
| selin.demir | AGENT | Insan Kaynaklari |
| oguz.kaya | AGENT | Insan Kaynaklari |
| merve.aksoy | AGENT | Insan Kaynaklari |
| cem.polat | AGENT | Muhasebe |
| deniz.eren | AGENT | Muhasebe |
| tolga.celik | AGENT | Muhasebe |
| busra.kurt | AGENT | Idari Isler |
| murat.dogan | AGENT | Idari Isler |
| irem.acar | AGENT | Idari Isler |
| sinan.erdogan | AGENT | Pazarlama |
| pelin.tunc | AGENT | Pazarlama |
| hasan.guler | AGENT | Pazarlama |
| yasemin.korkut | AGENT | Hukuk |
| berk.ciftci | AGENT | Hukuk |
| nazli.sezer | AGENT | Hukuk |

### Calisanlar (Employee — 35 hesap, sifre `pass123`)

Employee hesaplari `EMPLOYEE_NAMES` listesinden sirayla uretilir; departman `random.choice`
ile rastgele atanir (bu yuzden Departman sutunu listelenmemistir). Listenin ilk 2 hesabi pasiftir
(admin onayi bekliyor). `--users` artirildiginda liste basa donerek tekrar kullanilir.

| Nickname | Rol | Durum |
| --- | --- | --- |
| ali.korkmaz | EMPLOYEE | Pasif (onay bekliyor) |
| esra.yalcin | EMPLOYEE | Pasif (onay bekliyor) |
| serkan.ozturk | EMPLOYEE | Aktif |
| gamze.kaplan | EMPLOYEE | Aktif |
| onur.gunes | EMPLOYEE | Aktif |
| derya.avci | EMPLOYEE | Aktif |
| kadir.cakir | EMPLOYEE | Aktif |
| sibel.sen | EMPLOYEE | Aktif |
| ufuk.aktas | EMPLOYEE | Aktif |
| neslihan.koc | EMPLOYEE | Aktif |
| baris.yildiz | EMPLOYEE | Aktif |
| pinar.bozkurt | EMPLOYEE | Aktif |
| tuncay.karaca | EMPLOYEE | Aktif |
| hulya.turk | EMPLOYEE | Aktif |
| volkan.aslan | EMPLOYEE | Aktif |
| ceren.ucar | EMPLOYEE | Aktif |
| gokhan.bayrak | EMPLOYEE | Aktif |
| tugba.gul | EMPLOYEE | Aktif |
| erdem.balci | EMPLOYEE | Aktif |
| melis.duman | EMPLOYEE | Aktif |
| kerem.sari | EMPLOYEE | Aktif |
| asli.yavuz | EMPLOYEE | Aktif |
| berkay.topal | EMPLOYEE | Aktif |
| funda.erkan | EMPLOYEE | Aktif |
| caner.tekin | EMPLOYEE | Aktif |
| sule.erdem | EMPLOYEE | Aktif |
| levent.akkaya | EMPLOYEE | Aktif |
| yildiz.pekcan | EMPLOYEE | Aktif |
| mert.toprak | EMPLOYEE | Aktif |
| cansu.bilgin | EMPLOYEE | Aktif |
| burhan.karadag | EMPLOYEE | Aktif |
| damla.yener | EMPLOYEE | Aktif |
| sezer.coban | EMPLOYEE | Aktif |
| tulay.erol | EMPLOYEE | Aktif |
| furkan.aybar | EMPLOYEE | Aktif |

Not: Varsayilan 60 kullanici icin ilk 35 isim kullanilir (manager 6 + agent 18 + admin 1 = 25,
geri kalan 35 slot employee). `--users 60` altinda bu liste degismez.

## Biletler (varsayilan: 250)

### Yasam Dongusu Dagilimi (organik)
Hedef yuzdelikler — toplam 100:
- OPEN: 12% (atanmamis, bekliyor)
- IN_PROGRESS: 18% (ustlenildi, calisiliyor)
- RESOLVED: 15% (cozuldu, talep sahibi onayi bekliyor)
- CLOSED: 50% (onaylanmis veya 3 gun sonra otomatik kapanmis)
- ESCALATED: 5% (3 kez reddedilmis, mudahale gerekli)

### Oncelik Dagilimi
LOW (1/6), NORMAL (3/6), HIGH (1/6), URGENT (1/6)

### Tarih ve Sure
- created_at son `--days` (default 90) gun icine rastgele dagitilir; geriye tarihlenirken
  `sla_due_at` (calisma saatleri bazli SLA hedefi) de yeni created_at'e gore yeniden hesaplanir
- Cozum suresi onceliklere gore SLA `tickets/models.py:SLA_HOURS` tablosuna baglidir (IS SAATI):
  URGENT 4h, HIGH 24h, NORMAL 72h, LOW 168h
- SLA artik **calisma saatleri** (Pzt-Cuma 09:00-18:00) icinde sayilir; ihlal = bilet
  `sla_due_at`'ten sonra kapanmistir. Cozum suresi simulasyonu organik bir karisim uretir
  (bir kismi hedef icinde, bir kismi disinda kapanir)

### CSAT (Memnuniyet Puani)
- CLOSED biletlerin %75'inde CSAT puanlanir (otomatik kapanan biletlerin %30'unda)
- Puan dagilimi 4-5 yildiza agirlikli: weights = [3, 5, 12, 35, 45] for [1..5]

### Reopen / Eskalasyon
- CLOSED biletlerin %15'i 1-2 kez reddetme dongusunden gecer (reopen_count = 1 veya 2)
- ESCALATED biletler: 3 kez RESOLVED → RESOLUTION_REJECTED → en son escalate edilir
  (`escalated_at`, `rejection_reason`, `reopen_count = 3`)

### Etiket / Yorum
- Bilet basina 0-3 etiket (rastgele)
- Bilet basina 0-2 yorum (sender ve agent karisik)

### TicketHistory action_type Dagilimi
Her bilette en az `CREATED`, ataman varsa `TAKEN`, cozum surecinde `RESOLVED`,
red akiminda `RESOLUTION_REJECTED`, kapanis turune gore `RESOLUTION_CONFIRMED` veya `AUTO_CLOSED`,
escalate olanlarda `ESCALATED`, CSAT verilenlerde `CSAT_RATED`.

## Bildirimler
- Atama bildirimi: bilet ustlenildiginde sender'a
- RESOLVED bildirimi: bilet cozuldu olarak isaretlendiginde sender'a (onay isteni)
- CLOSED bildirimi: kapanan biletlerde sender'a
- ESCALATED bildirimi: tum departman yoneticilerine (multi-manager)
- Pasif kullanici onayi bildirimi: admin'e

## Audit Log
- Rastgele 25 kullanici icin `Giris basarili` kaydi (AUTH)
- Her departman icin olusturma kaydi (DEPARTMENT)
- En fazla 20 bilet icin olusturma kaydi (TICKET)

## Default Kosulda Beklenen Metrikler

`seed_demo --reset` (default) ile rapor sayfasi suralari karsilamak uzere yeterli veri ureyir:
- ~30 OPEN + ~37 IN_PROGRESS bilet → "Aktif yuk" gostergeleri
- ~40 RESOLVED → "Onayinizi bekliyor" listesi (employee dashboard)
- ~120 CLOSED → SLA uyum oranlari, CSAT histogrami, ortalama cozum suresi
- ~20 ESCALATED → kirmizi cerceveli eskalasyon kartlari, mudahale alarmlari
- ~80 CSAT puani, ~40 reopen → reopen-rate ve memnuniyet siralamalari
- 90 gunluk tarih araligi → trend grafiginde gun/hafta/ay granuluterelerinin tamami calisir
