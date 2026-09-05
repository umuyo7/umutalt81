-- =========================================================
-- Catering ve Yemek Dağıtım Yönetim Sistemi - Veritabanı Şeması
-- InfinityFree phpMyAdmin üzerinden içe aktarılabilir.
-- =========================================================

-- Eğer veritabanınızı zaten InfinityFree panelinden oluşturduysanız
-- (InfinityFree kullanıcıları yeni veritabanı oluşturamaz, bu normaldir)
-- phpMyAdmin'de kendi veritabanınızı seçili haldeyken bu dosyayı
-- doğrudan import edin; aşağıdaki tablolar o veritabanına eklenecektir.

-- ---------------------------------------------------------
-- 1) musteriler
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS musteriler (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    sirket_ismi             VARCHAR(150) NOT NULL,
    sahis_adi               VARCHAR(150) DEFAULT NULL,
    telefon                 VARCHAR(20)  DEFAULT NULL,
    eposta                  VARCHAR(150) DEFAULT NULL,
    adres                   TEXT         DEFAULT NULL,
    anlasilan_yemek_fiyati  DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    mesai_yemek_fiyati      DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    varsayilan_kisi_sayisi  INT NOT NULL DEFAULT 0,
    faturali_mi             TINYINT(1) NOT NULL DEFAULT 0,
    devreden_borc           DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    aktif_mi                TINYINT(1) NOT NULL DEFAULT 1,
    kayit_tarihi            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- 2) gunluk_yemek_verileri
-- Not: (musteri_id, tarih) üzerinde UNIQUE anahtar var; böylece
-- aynı müşteri için aynı gün ikinci kez kayıt girilirse
-- gunluk_giris.php sayfası veriyi GÜNCELLER (upsert), tekrar eklemez.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS gunluk_yemek_verileri (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    musteri_id            INT NOT NULL,
    tarih                 DATE NOT NULL,
    yemek_adedi           INT NOT NULL DEFAULT 0,
    gunluk_toplam_tutar   DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    mesai_yemek_adedi     INT NOT NULL DEFAULT 0,
    mesai_toplam_tutar    DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    olusturma_tarihi      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_musteri_tarih (musteri_id, tarih),
    CONSTRAINT fk_gyv_musteri FOREIGN KEY (musteri_id)
        REFERENCES musteriler(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- 2b) taziye_yemekleri
-- Tek seferlik taziye yemeği kayıtları. HER ZAMAN tek seferliktir;
-- kayıtlı müşteri listesiyle hiçbir bağlantısı yoktur ve bu yüzden
-- hiçbir müşterinin cari hesap ekstresine/PDF'ine dahil edilmez.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS taziye_yemekleri (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    firma_adi           VARCHAR(150) NOT NULL,
    tarih               DATE NOT NULL,
    adet                INT NOT NULL DEFAULT 0,
    birim_fiyat         DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    toplam_tutar        DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    aciklama            VARCHAR(255) DEFAULT NULL,
    olusturma_tarihi    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- 3) tahsilatlar
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS tahsilatlar (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    musteri_id          INT NOT NULL,
    tarih               DATE NOT NULL,
    tutar               DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    aciklama            VARCHAR(255) DEFAULT NULL,
    olusturma_tarihi    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tah_musteri FOREIGN KEY (musteri_id)
        REFERENCES musteriler(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- 3a) Günlük giderler
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS gunluk_giderler (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    tarih               DATE NOT NULL,
    kategori            VARCHAR(100) NOT NULL DEFAULT 'Diğer',
    aciklama            VARCHAR(255) NOT NULL,
    tutar               DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    olusturma_tarihi    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_gider_tarih (tarih)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- 3b) Çalışanlar ve maaş ödemeleri
-- Aylık maaş, fiilen ödenen tutar ve ödeme dönemi ayrı tutulur;
-- böylece avans/taksit gibi birden fazla ödeme de kaydedilebilir.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS calisanlar (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    ad_soyad            VARCHAR(150) NOT NULL,
    gorev               VARCHAR(100) DEFAULT NULL,
    telefon             VARCHAR(20) DEFAULT NULL,
    aylik_maas          DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    ise_giris_tarihi    DATE DEFAULT NULL,
    aktif               TINYINT(1) NOT NULL DEFAULT 1,
    olusturma_tarihi    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS maas_odemeleri (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    calisan_id          INT NOT NULL,
    donem               DATE NOT NULL,
    tarih               DATE NOT NULL,
    tutar               DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    aciklama            VARCHAR(255) DEFAULT NULL,
    olusturma_tarihi    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_maas_calisan_donem (calisan_id, donem),
    CONSTRAINT fk_maas_calisan FOREIGN KEY (calisan_id)
        REFERENCES calisanlar(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- 4) ekstreler
-- Oluşturulan her PDF cari hesap ekstresinin/faturasının
-- değerlerini saklar; geçmişten tekrar indirilebilmesini sağlar.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS ekstreler (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    musteri_id              INT NOT NULL,
    baslama_tarihi          DATE NOT NULL,
    bitis_tarihi            DATE NOT NULL,
    gun_sayisi              INT NOT NULL DEFAULT 0,
    kisi_sayisi             INT NOT NULL DEFAULT 0,
    normal_yemek_adedi      INT NOT NULL DEFAULT 0,
    normal_yemek_fiyati     DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    normal_yemek_tutari     DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    mesai_yemek_adedi       INT NOT NULL DEFAULT 0,
    mesai_yemek_fiyati      DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    mesai_yemek_tutari      DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    fazla_yemek_adedi       INT NOT NULL DEFAULT 0,
    fazla_yemek_fiyati      DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    fazla_yemek_tutari      DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    onceki_bakiye           DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    donem_ara_toplami       DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    kdv_orani               DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    kdv_tutari              DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    donem_toplami           DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    alinan_avans            DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    kalan_bakiye            DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    olusturma_tarihi        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ekstre_musteri FOREIGN KEY (musteri_id)
        REFERENCES musteriler(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------
-- Zaten "durum" (aktif/pasif) kolonu ile kurulum yapmış olanlar için
-- (bu kolon artık kullanılmıyor; isterseniz kaldırabilirsiniz):
-- ---------------------------------------------------------
-- ALTER TABLE musteriler DROP COLUMN durum;

-- ---------------------------------------------------------
-- ⚠️ ZATEN KURULU (eski) bir veritabanınız varsa, yukarıdaki yeni
-- sütunları/tabloları eklemek için sadece aşağıdaki migration.sql
-- dosyasını çalıştırmanız yeterlidir (bu dosyayı tekrar import
-- etmenize gerek yoktur, CREATE TABLE IF NOT EXISTS zaten var olan
-- tabloları atlar ama yeni sütunları otomatik eklemez).
-- ---------------------------------------------------------

-- ---------------------------------------------------------
-- (Opsiyonel) Test verisi eklemek isterseniz:
-- ---------------------------------------------------------
-- INSERT INTO musteriler (sirket_ismi, sahis_adi, telefon, eposta, adres, anlasilan_yemek_fiyati)
-- VALUES ('ABC Lojistik A.Ş.', 'Ahmet Yılmaz', '05551234567', 'ahmet@abc.com', 'İstanbul', 45.00);
