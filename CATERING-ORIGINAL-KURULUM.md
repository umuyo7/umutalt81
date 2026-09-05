# Orijinal Catering Sistemini Ekleme

Bu güncelleme, kullanıcının `bereketcatering.zip` dosyasındaki PHP ekranlarını değiştirmeden catering hesabına bağlar. Eski `config.php` içindeki InfinityFree parolaları ve eski oturum dosyaları pakete alınmamıştır.

## 1. Ortam ayarları

Üç ayrı güçlü değer üretin:

```bash
openssl rand -hex 32
openssl rand -hex 24
openssl rand -hex 24
```

`.env` dosyasına ekleyin:

```env
CATERING_SSO_SECRET=BIRINCI_CIKTI
CATERING_DB_HOST=catering_db
CATERING_DB_NAME=bereket_catering
CATERING_DB_USER=bereket_user
CATERING_DB_PASSWORD=IKINCI_CIKTI
CATERING_DB_ROOT_PASSWORD=UCUNCU_CIKTI
```

`APP_PREFIX=/xyz` ve `COOKIE_HTTPS_ONLY=true` olarak kalmalıdır.

## 2. Servisleri başlatma

```bash
cd /opt/restaurant-catering
docker compose up -d --build
docker compose ps
docker compose logs --tail=50 app catering catering_db
```

Catering PHP servisi yalnız `127.0.0.1:8081` adresinden dinler.

## 3. aaPanel reverse proxy

Mevcut `/xyz/ -> http://127.0.0.1:8000/` kuralına dokunmayın. İkinci kuralı ekleyin:

```text
Proxy name: bereket-catering
Proxy directory: /xyz/catering/
Target URL: http://127.0.0.1:8081/
Sending host: $host
Cache: kapalı
```

Hedef URL'nin sonundaki `/` korunmalıdır. Nginx en uzun eşleşmeyi seçtiğinden `/xyz/catering/` PHP sistemine, diğer `/xyz/` adresleri ana giriş/restoran uygulamasına gider.

## 4. InfinityFree verisini taşıma

InfinityFree phpMyAdmin'de doğru veritabanını seçin ve **Export > Custom > SQL** ile tüm tabloları dışa aktarın. Mümkünse `Add DROP TABLE` seçeneğini açın. İnen dosyayı sunucuda şu konuma yükleyin:

```text
/opt/restaurant-catering/imports/infinityfree.sql
```

İçe aktarın:

```bash
cd /opt/restaurant-catering
docker compose exec -T catering_db sh -c 'mariadb -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"' < imports/infinityfree.sql
```

Kontrol edin:

```bash
docker compose exec catering_db sh -c 'mariadb -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE" -e "SHOW TABLES;"'
```

## 5. Giriş akışı

- `/xyz/` ortak giriş ekranıdır.
- Catering kullanıcısı başarılı girişten sonra orijinal PHP catering sistemine aktarılır.
- Restoran kullanıcısı mevcut restoran panelinde kalır.
- Catering sistemindeki Çıkış düğmesi iki oturumu da kapatıp ortak girişe döner.
