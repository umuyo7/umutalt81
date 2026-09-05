# Bereket Sofram POS — uygulama durumu

## Tamamlanan kapsam

- Mevcut catering ve restoran veri alanları korunarak profesyonel POS modülü aynı FastAPI uygulamasına eklendi.
- Beş sistem rolü ve 31 granular permission; rol grant/deny, kullanıcı override ve indirim limiti eklendi.
- Argon2 parola üretimi, eski scrypt parolalarda başarılı giriş sonrası otomatik rehash, başarısız giriş kilidi ve veritabanı tabanlı iptal edilebilir oturum eklendi.
- Salon, masa, kategori, ürün ve restoran personeli tanımları eklendi.
- Masa açma, kişi sayısı, garson devri, masa taşıma, adisyon birleştirme ve ürün/adet bazında başka boş masaya bölme eklendi.
- Ürün ekleme, miktar değiştirme, iptal, ikram, fiyat override, yüzde/sabit tutar indirim ve indirim kaldırma eklendi.
- Nakit, kredi kartı, yemek kartı, havale ve diğer ödeme yöntemleri; parçalı/karma ödeme ve idempotent tahsilat eklendi.
- Hesap talebi olmadan ödeme alma için açık uyarı/audit; ödeme ters kaydı, yöntem düzeltme, zorla kapama ve yeniden açma eklendi.
- Audit log, transactional outbox, SSE canlı güncelleme, PWA manifest/service worker ve mobil uyumlu arayüz eklendi.
- Günlük KPI ile tarih aralıklı yönetim raporu; garson, ürün, kategori, saat, ödeme yöntemi ve ödeme bağlamı kırılımları ile UTF-8 CSV dışa aktarımı eklendi.
- Kullanıcı rol/aktiflik, salon/masa ve kategori/ürün düzenleme–soft archive işlemleri ile admin rol-permission matrisi API'si eklendi.
- Request ID, CSP, HSTS (production HTTPS), clickjacking, MIME sniffing, referrer ve tarayıcı izin başlıkları eklendi.
- Catering `payments` tablosu veri koruyan migration ile `catering_payments` adına ayrıldı; POS ödemeleri bağımsız `payments` tablosuna alındı.
- Production başlangıcı Alembic `head` zorunluluğuyla korundu; toplam beş migration revision'ı bulunuyor.
- PostgreSQL native enum tipleri migration içinde tek sefer oluşturulacak şekilde doğrulandı; PostgreSQL offline SQL zinciri `0001`–`0005` için başarıyla üretildi.

## Doğrulama sonucu

4 Eylül 2026 tarihinde aşağıdaki kontroller başarıyla tamamlandı:

- `tests/smoke.py`
- `tests/auth_separation.py`
- `tests/migration_smoke.py`
- `tests/permission_smoke.py`
- `tests/pos_service_flow.py`
- `tests/pos_merge_split.py`
- `tests/pos_api_flow.py`
- `python -m compileall app tests`
- `alembic check`: `No new upgrade operations detected.`

Permission seed idempotenttir: 5 rol, 31 permission ve 83 rol grant'i.

## Canlıya geçişten önce zorunlu kabul kontrolü

Bu çalışma ortamında Docker istemcisi mevcut olsa da Docker daemon/PostgreSQL servisi çalışmadığı için migration zinciri gerçek PostgreSQL 16 üzerinde yürütülemedi. SQLite tabanlı migration ve servis/API testleri geçti. Canlıya almadan önce yedek/restore provasıyla birlikte staging PostgreSQL 16 üzerinde şu kontroller zorunludur:

1. Mevcut veritabanında `alembic stamp 0001_existing_schema_baseline` ve `alembic upgrade head`.
2. `catering_payments` satır/adet ve toplam tutar mutabakatı.
3. Aynı masada eşzamanlı servis açma ve aynı adisyona eşzamanlı tahsilat yarışı.
4. Partial unique index, enum ve `SELECT ... FOR UPDATE` davranışı.
5. Nginx HTTPS, gerçek alan adı, güvenli `.env`, yedekleme ve restore testi.

Bu maddeler kod eksiği değil, hedef altyapıda yapılması gereken üretim kabul testleridir.
