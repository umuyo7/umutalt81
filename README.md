# Bereket Yönetim — Contabo kurulumu

## Veritabanı migration notu

Şema artık Alembic ile sürümlenir. `app` servisini yeni kodla başlatmadan önce migration çalıştırılmalıdır.

### Var olan canlı PostgreSQL kurulumu

Mevcut tablolar zaten varsa başlangıç revision'ını **çalıştırmayın**. Önce yedek ve restore provası yapın; ardından:

```bash
docker compose run --rm app alembic stamp 0001_existing_schema_baseline
docker compose run --rm app alembic upgrade head
```

İkinci komut mevcut catering `payments` tablosunu, satırları koruyarak `catering_payments` adına taşır. Uygulama kodu ve migration aynı deployment içinde alınmalıdır.

POS sistem rollerini ve granular permission kayıtlarını idempotent biçimde oluşturun:

```bash
docker compose run --rm app python -m app.seed_pos_permissions
```

### Boş/yeni PostgreSQL kurulumu

```bash
docker compose run --rm app alembic upgrade head
docker compose run --rm app python -m app.seed_pos_permissions
```

Migration tamamlanmadan yeni uygulama image'ını çalıştırmayın. Uygulama production başlangıcında Alembic revision'ını kontrol eder ve şema `head` değilse çalışmayı reddeder. Production'da `alembic downgrade` ile finansal veri silen geri dönüş uygulanmaz; sorun halinde yeni özellik kapatılır ve yedekten/forward migration ile düzeltilir.

Tek uygulama içinde iki ayrı yetki alanı vardır:

- Catering kullanıcısı yalnız müşteri, günlük yemek, ödeme ve catering ekstrelerini görür.
- Restoran kullanıcısı yalnız ciro, gider, çalışan, maaş ve restoran raporlarını görür.

`umut` ve `ahmet` zorunlu değildir; kullanıcı adlarını `.env` dosyasında siz belirlersiniz. Dışarıdan hesap açma kapalıdır.

## POS ekranları

- `/pos/masalar`: salon/masa görünümü ve servis açma
- `/pos/adisyon/{id}`: ürün ekleme, adet, not, hesap talebi ve adisyon özeti
- `/kasa`: açık adisyonlar ve tahsilat
- `/yonetim`: operasyon özeti ve günlük KPI'lar
- `/yonetim/adisyon/{id}`: indirim, ikram, iptal, fiyat, taşıma, devir, birleştirme/bölme ve finansal düzeltmeler
- `/yonetim/tanimlar`: salon, masa, kategori, ürün ve kullanıcı tanımları

REST API `/api/v1` altındadır. Yazma işlemlerinde CSRF başlığı; tahsilatta ayrıca `Idempotency-Key` zorunludur. Canlı masa/adisyon yenilemeleri SSE üzerinden `/api/v1/events` ile yayınlanır. Günlük rapor CSV çıktısı `/api/v1/reports/daily.csv`, tarih aralıklı ayrıntılı rapor ve CSV çıktıları `/api/v1/reports/operations` ile `/api/v1/reports/operations.csv` adreslerindedir.

Oturumlar imzalı, HTTPS-only çereze ek olarak `login_sessions` tablosunda tutulur; çıkışta iptal edilir ve varsayılan 12 saatte sona erer. Bu süre `SESSION_TTL_HOURS` ile 1–168 saat arasında ayarlanabilir.

## MariaDB üzerinde çalışan FastAPI catering ekranları

PHP catering bölümünün FastAPI karşılığı `/catering-native/` altında bulunur. Bu bölüm mevcut MariaDB tablolarını doğrudan kullanır; tablo oluşturmaz, migration çalıştırmaz ve veriyi başka veritabanına taşımaz. İlk kurulumda kapalı ve salt okunur bırakılır:

```dotenv
CATERING_NATIVE_ENABLED=false
CATERING_NATIVE_READONLY=true
CATERING_BACKEND=php
```

Canlı şemayı yalnız `SELECT` sorgularıyla kontrol etmek için:

```bash
docker compose -p restaurant-catering run --rm --no-deps app python -m app.catering_check
```

Kontrol başarılı olduktan sonra önce `CATERING_NATIVE_ENABLED=true` yapıp salt okunur önizlemeyi açın. `/catering-native/` ekranları ve PDF'ler doğrulandıktan sonra `CATERING_NATIVE_READONLY=false` ve `CATERING_BACKEND=native` yapılarak yazma ve yeni yönlendirme açılır. PHP container'ı ile MariaDB volume'u geri dönüş için yerinde tutulur.

## Yerel doğrulama

Geliştirme bağımlılıklarını kurduktan sonra:

```bash
python tests/smoke.py
python tests/auth_separation.py
python tests/migration_smoke.py
python tests/permission_smoke.py
python tests/pos_service_flow.py
python tests/pos_merge_split.py
python tests/pos_api_flow.py
alembic check
```

## 1. Contabo'da başlatma

Projeyi `/opt/restaurant-catering` dizinine yükleyin:

```bash
cd /opt/restaurant-catering
cp .env.example .env
openssl rand -hex 32
nano .env
```

`.env` içinde şunları mutlaka değiştirin:

- `SESSION_SECRET`: `openssl rand -hex 32` çıktısı
- `POSTGRES_PASSWORD`: güçlü, size özel veritabanı şifresi
- `DATABASE_URL`: içindeki `CHANGE_ME` yerine aynı veritabanı şifresi
- `CATERING_USERNAME` ve `CATERING_PASSWORD`
- `RESTAURANT_USERNAME` ve `RESTAURANT_PASSWORD`
- `APP_PREFIX`: Alt yol kullanılacaksa `/giris/xyz`; tüm alan adı uygulamaya ayrılacaksa boş bırakın

Şifreler en az 12 karakter olsun. Ardından:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx
docker compose up -d --build
docker compose ps
```

Not: Hesaplar ilk açılışta oluşturulur. Daha sonra `.env` içindeki parolayı değiştirmek veritabanındaki mevcut parolayı otomatik değiştirmez.

## 2. InfinityFree verisini dışarı alma

1. `scripts/export-infinityfree.php` dosyasını eski InfinityFree sitesinde `config.php` ile aynı ana dizine yükleyin.
2. Eski yönetim paneline normal şekilde giriş yapın.
3. Tarayıcıda `https://ESKI-ALAN-ADINIZ/export-infinityfree.php` adresini açın.
4. İnen `bereket-infinityfree-....json` dosyasını güvenli bir yerde saklayın.
5. `export-infinityfree.php` dosyasını InfinityFree'den hemen silin.

Dışa aktarılan tablolar: müşteriler, günlük yemekler, tahsilatlar, taziye yemekleri, giderler, çalışanlar, maaş ödemeleri ve eski ekstre arşivi.

## 3. JSON verisini Contabo'ya aktarma

İndirilen JSON dosyasını Contabo'da proje içindeki `imports` klasörüne yükleyin. Örnek:

```bash
scp bereket-infinityfree-20260904-120000.json root@SUNUCU_IP:/opt/restaurant-catering/imports/
```

Sonra sunucuda:

```bash
cd /opt/restaurant-catering
docker compose exec app python -m app.import_legacy /imports/bereket-infinityfree-20260904-120000.json
```

Aktarıcı aynı dosyayı ikinci kez almaz ve hedefte işletme verisi varsa çoğaltma riskine karşı durur. İşlem sonunda her tablonun aktarılan kayıt sayısını gösterir.

Eşleştirme:

- Müşteri, yemek, tahsilat, taziye ve ekstre → catering hesabı
- Gider, çalışan ve maaş → restoran hesabı
- Eski sistemde restoran cirosu tablosu olmadığı için ciro bölümü boş başlar

## 4. Alan adı ve HTTPS

`/etc/nginx/sites-available/bereket` örneği:

```nginx
server {
    server_name panel.ornekalanadiniz.com;
    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/bereket /etc/nginx/sites-enabled/bereket
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d panel.ornekalanadiniz.com
```

HTTPS kurulmadan test edecekseniz `.env` içinde geçici olarak `COOKIE_HTTPS_ONLY=false` yapın. Alan adı ve HTTPS hazır olunca tekrar `true` yapıp `docker compose up -d` çalıştırın.

### aaPanel'de alt yol kullanımı

`APP_PREFIX=/giris/xyz` ise Nginx/aaPanel reverse proxy dizini `/giris/xyz/`, hedef adresi ise `http://127.0.0.1:8000/` olmalıdır. Hedefteki sondaki `/` işareti korunmalıdır. `/giris/xyz` adresini `/giris/xyz/` adresine yönlendirin.

## 5. Günlük PostgreSQL yedeği

```bash
sudo chmod +x /opt/restaurant-catering/scripts/backup-postgres.sh
crontab -e
```

Her gece 02:30 için:

```cron
30 2 * * * /opt/restaurant-catering/scripts/backup-postgres.sh
```

Yedekler `/opt/backups/restaurant-catering` altında 30 gün tutulur. Betik boş veya bozuk yedeği başarılı saymaz.

## Güvenlik notu

Eski InfinityFree `config.php` dosyasında veritabanı ve yönetici şifreleri düz metin tutuluyordu. Taşıma tamamlandıktan sonra bu parolaları InfinityFree panelinden değiştirin; eski siteyi kapatacaksanız veritabanı dışa aktarımını ve son yedeği aldıktan sonra kapatın.
