# Catering ve Yemek Dağıtım Yönetim Sistemi

Saf PHP (PDO) + MySQL + Tailwind CSS (CDN) + Chart.js (CDN) ile yazılmıştır.
Composer veya framework gerektirmez — InfinityFree gibi ücretsiz paylaşımlı
hostinglerde doğrudan çalışır. Şifre ile korumalı, mobil öncelikli tasarım.

## Dosya Yapısı

```
catering-sistemi/
├── config.php              # Veritabanı bağlantısı + admin şifresi + firma bilgileri
├── database.sql            # Kurulacak tablolar (yeni kurulum)
├── migration_v2.sql        # Mesai/Taziye/Ekstre özellikleri için ESKİ kurulumlarda çalıştırılır
├── login.php                # Giriş (şifre) ekranı
├── logout.php                # Çıkış işlemi
├── index.php                # Dashboard (istatistik kartları + grafik)
├── musteriler.php           # Müşteri ekleme / listeleme (normal + mesai fiyatı)
├── gunluk_giris.php         # Günlük yemek adedi girişi (normal + mesai)
├── musteri_detay.php        # Müşteri hesap ekstresi + PDF geçmişi
├── taziye_ekle.php          # Tek seferlik taziye yemeği kayıtları (müşteriden bağımsız)
├── ekstre_olustur.php       # Dönemsel ekstre/fatura sihirbazı (2 adım)
├── ekstre_pdf.php           # Profesyonel, logolu PDF ekstre üretici (TCPDF)
├── assets/
│   └── logo-header.png      # Firma logosu (PDF üst başlığında kullanılır)
├── vendor/tcpdf/             # PDF kütüphanesi (Composer gerekmez, doğrudan çalışır)
└── includes/
    ├── auth.php             # Oturum kontrolü (korumalı sayfalarda kullanılır)
    ├── header.php           # Üst bar + masaüstü/mobil menü
    ├── footer.php           # Alt menü (bottom navigation)
    ├── functions.php
    ├── EkstrePDF.php         # TCPDF tabanlı kurumsal PDF şablonu
    └── session_data/         # PHP oturum dosyaları (yazma izni gerekir)
```

## Kurulum Adımları (InfinityFree)

1. **Veritabanı oluşturun / mevcut olanı kullanın** ve `database.sql` dosyasını
   phpMyAdmin üzerinden import edin (veritabanınızı seçili tutarak "Import"
   sekmesinden yükleyin). **Zaten kurulu bir veritabanınız varsa**, bunun
   yerine sadece `migration_v2.sql` dosyasını çalıştırın (mevcut verileri silmez).

2. **`config.php` dosyasını düzenleyin**
   - `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASS`: panelinizden aldığınız bilgiler.
   - `ADMIN_PASSWORD`: **sisteme giriş şifresi** — mutlaka değiştirin!
   - `FIRMA_ADI`, `FIRMA_ADRES`, `FIRMA_TELEFON`: PDF ekstrelerin altında görünür.

3. **Dosyaları yükleyin**
   Tüm klasörü (`config.php`, `*.php`, `includes/`, `assets/`, `vendor/`)
   FTP veya dosya yöneticisi ile `htdocs/` klasörünüzün içine yükleyin.
   ⚠️ **Önceden farklı bir PDF kütüphanesi (ör. `lib/tfpdf/`) yüklediyseniz
   o klasörü silin** — artık `vendor/tcpdf/` kullanılıyor, çakışmasın.

4. **Canlıya aldıktan sonra**
   `config.php` içindeki `ini_set('display_errors', 1);` satırını `0` yaparak
   hata mesajlarının ziyaretçilere görünmesini engelleyin.

## Giriş Sistemi

Sisteme herhangi bir sayfadan girmeye çalıştığınızda, giriş yapılmamışsa
otomatik olarak `login.php`'ye yönlendirilirsiniz. `config.php` içindeki
`ADMIN_PASSWORD` değeri ile giriş yapılır. Kullanıcı adı yoktur, tek bir
şifre yeterlidir. Sağ üstteki "Çıkış" butonu ile oturumu kapatabilirsiniz.

## PDF Ekstre / Fatura Nasıl Oluşturulur?

1. `musteri_detay.php` sayfasında ilgili müşterinin **"Ekstre / Fatura
   Oluştur (PDF)"** butonuna tıklayın.
2. **1. Adım**: dönemin başlama/bitiş tarihini ve kişi sayısını girin,
   "Devam Et" deyin.
3. **2. Adım**: sistem, günlük girişlerden ve önceki bakiyeden otomatik
   öneriler hesaplar (kişi × gün, mesai yemeği, önceki bakiye, alınan
   avans). Gerekirse üzerine yazıp düzeltebilirsiniz — özellikle kağıt
   kayıtlardan gelen eski "önceki bakiye" değerini ilk seferde elle
   girmeniz gerekebilir.
4. **"PDF Oluştur ve İndir"** dediğinizde, firma logonuzla, kurumsal
   renklerle hazırlanmış PDF açılır ve `ekstreler` tablosuna kaydedilir
   (müşteri detay sayfasındaki "Oluşturulan Ekstreler" listesinden
   tekrar erişebilirsiniz).

## Taziye Yemeği

`taziye_ekle.php` sayfasından girilir. **Her zaman tek seferliktir**;
kayıtlı müşteri listesiyle hiçbir bağlantısı yoktur, firma/kişi adı her
seferinde serbestçe yazılır ve **hiçbir müşterinin ekstre/PDF'ine
dahil edilmez** — tamamen ayrı, bağımsız bir kayıt defteridir.

## Kullanım Notları

- **Aktif/Pasif durum kaldırıldı**: Artık tüm müşteriler her zaman günlük
  giriş listesinde görünür; ayrı bir durum yönetimi yoktur.
- **Aynı gün tekrar giriş**: `gunluk_yemek_verileri` tablosunda
  `(musteri_id, tarih)` üzerinde UNIQUE anahtar vardır. Aynı tarih için
  tekrar kayıt girilirse veri **güncellenir** (üzerine yazılır), mükerrer
  satır oluşmaz.
- **Mesai yemeği**: Her müşterinin normal fiyatından farklı, ayrı bir
  mesai yemeği birim fiyatı olabilir (`musteriler.php`'de tanımlanır).
  Günlük girişte normal ve mesai adedi ayrı ayrı girilir.
- **Mobil öncelikli tasarım**: Küçük ekranlarda alt kısımda sabit bir
  menü (Panel / Müşteriler / Günlük Giriş / Taziye Yemekleri) görünür;
  masaüstünde bu menü üst barda sekmeler halinde gösterilir.
- **Güvenlik**: Tüm veritabanı sorgularında PDO prepared statement
  kullanılmıştır. Tüm kullanıcı çıktıları `h()` fonksiyonu ile
  `htmlspecialchars`'tan geçirilir (XSS koruması). Giriş şifresi
  `hash_equals()` ile zamanlama saldırılarına karşı güvenli şekilde
  karşılaştırılır.
