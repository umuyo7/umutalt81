# Rapor ve PDF güncellemesi

Bu paket yalnızca mevcut catering uygulamasındaki rapor ve PDF dosyalarını
günceller. FastAPI restoran ekranlarına ve kullanıcı hesaplarına dokunmaz.

## Sunucuda kurulum

Paketi `/opt/restaurant-catering` içine açtıktan sonra:

```bash
cd /opt/restaurant-catering
docker compose build --no-cache catering
docker compose up -d catering
docker compose exec catering php -m | grep -E 'mbstring|gd|pdo_mysql'
```

Son komutun çıktısında `mbstring`, `gd` ve `pdo_mysql` görünmelidir.

## Daha önce JSON verisi içe aktarıldıysa

Önce MariaDB yedeği alın:

```bash
cd /opt/restaurant-catering
mkdir -p backups
docker compose exec -T catering_db sh -c 'mariadb-dump -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"' > "backups/pdf-duzeltme-oncesi-$(date +%Y%m%d-%H%M%S).sql"
```

Ardından eski ekstre ara toplamlarını düzeltin:

```bash
docker compose exec -T catering_db sh -c 'mariadb -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"' < catering-php/migration_v7_rapor_pdf_duzeltme.sql
```

## JSON verisi henüz içe aktarılmadıysa

Paket içindeki düzeltilmiş `imports/infinityfree-catering-verileri.sql`
dosyasını kullanın. Bu dosya eski ekstre ara toplamlarını aktarım sırasında
otomatik düzeltir.

```bash
docker compose exec -T catering_db sh -c 'mariadb -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"' < imports/infinityfree-catering-verileri.sql
```

## Kontrol

1. `https://bereketsofram.com/xyz/` üzerinden catering hesabıyla giriş yapın.
2. Raporlama ekranında seçilen gün, seçilen ay ve genel durumun ayrı olduğunu kontrol edin.
3. Bir müşterinin geçmiş ekstresinden **Özet PDF** ve **Gün Gün Detay PDF** bağlantılarını açın.

