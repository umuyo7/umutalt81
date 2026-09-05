# v2 Güncellemesi - Yapılanlar ve Kurulum

## Neler eklendi?
1. **PDF Makbuz** — Müşteri detay sayfasından "PDF Makbuz Oluştur" ile bir
   tarih aralığı seçilip logolu, profesyonel bir PDF makbuz indirilebiliyor
   (Bereket Sofram logonuz makbuzun üst kısmında banner olarak kullanılıyor).
2. **Mesai Yemeği** — Her müşterinin normal yemek fiyatının yanında ayrı bir
   "mesai yemeği fiyatı" tanımlanabiliyor. Günlük Giriş ekranında normal
   adedin yanına ikinci bir "mesai adedi" sütunu eklendi.
3. **Taziye Yemekleri** — Tek seferlik, fiyatı değişken taziye yemeği
   kayıtları için yeni bir sayfa: **Taziye Yemekleri** (alt menüde).
4. Müşteri detay sayfasına **"Bilgileri Düzenle"** bölümü eklendi (önceden
   sadece ekleme vardı, artık mesai fiyatı / kişi sayısı gibi bilgiler
   sonradan da güncellenebiliyor).

## KURULUM — ÇOK ÖNEMLİ
Sitenizde zaten canlı bir veritabanı olduğu için önce şunu yapmalısınız:

1. phpMyAdmin'e girin, veritabanınızı seçin, üstteki **SQL** sekmesine tıklayın.
2. Bu klasördeki **`migration_v2.sql`** dosyasının içeriğini yapıştırıp
   **Çalıştır**'a basın. (Bu işlem mevcut verilerinizi SİLMEZ, sadece yeni
   sütun/tablo ekler.)
3. Ardından tüm dosyaları (özellikle `lib/`, `assets/`, `includes/`, ve yeni
   eklenen `taziye_yemekleri.php`, `pdf_olustur.php` dosyalarını) sunucunuza
   yükleyin. `config.php` dosyanızı **değiştirmeyin/üzerine yazmayın** —
   sizin veritabanı bilgileriniz onun içinde.

Sıfırdan kurulum yapacaklar için `database.sql` zaten güncel haliyle
hazırlandı, migration'a gerek yok.

## Bilmeniz gerekenler
- PDF oluşturma, üçüncü parti bir servise ihtiyaç duymuyor (composer
  gerektirmez), `lib/tfpdf` klasörü ile birlikte gelir — InfinityFree gibi
  paylaşımlı hostinglerde sorunsuz çalışır.
- Logo olarak gönderdiğiniz ekran görüntüsünü kullandım
  (`assets/logo.png`). Elinizde daha yüksek çözünürlüklü / orijinal bir logo
  dosyası varsa (örn. .png/.jpg, en az 1200px genişlikte), onu
  `assets/logo.png` olarak değiştirirseniz PDF çıktısındaki görüntü daha da
  net olur. Şu anki logo ekran görüntüsünden geldiği için PDF'te hafif
  bulanıklık olabilir.
- "Kişi Sayısı", "Fazla Yemek Adedi" ve "Alınan Avans" alanları PDF
  oluşturma ekranında elle giriliyor (Alınan Avans, o dönemdeki kayıtlı
  ödemelerden otomatik öneriliyor, isterseniz değiştirebilirsiniz).
- "Önceki Bakiye" ve dönem toplamları tamamen otomatik hesaplanıyor
  (seçtiğiniz başlangıç tarihinden önceki tüm hizmet - tüm ödemeler).
