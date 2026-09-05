-- =========================================================
-- MIGRATION v2 — PDF Ekstre / Mesai Yemeği / Taziye Yemeği Güncellemesi
-- =========================================================
-- Bu dosyayı SADECE zaten kurulu (eski) bir veritabanınız varsa
-- bir kereliğine çalıştırın. Yeni kurulumlarda database.sql zaten
-- bu sütun/tabloları içerir, bu dosyayı çalıştırmanıza gerek yoktur.
--
-- phpMyAdmin > veritabanınızı seçin > SQL sekmesi > bu dosyanın
-- tamamını yapıştırıp "Git/Çalıştır" deyin.
-- =========================================================

-- 1) Müşteriye "mesai yemeği" birim fiyatı ve varsayılan kişi sayısı ekle
ALTER TABLE musteriler
    ADD COLUMN mesai_yemek_fiyati DECIMAL(10,2) NOT NULL DEFAULT 0.00 AFTER anlasilan_yemek_fiyati,
    ADD COLUMN varsayilan_kisi_sayisi INT NOT NULL DEFAULT 0 AFTER mesai_yemek_fiyati;

-- 2) Günlük yemek verilerine mesai yemeği adet/tutar sütunları ekle
ALTER TABLE gunluk_yemek_verileri
    ADD COLUMN mesai_yemek_adedi INT NOT NULL DEFAULT 0 AFTER gunluk_toplam_tutar,
    ADD COLUMN mesai_toplam_tutar DECIMAL(10,2) NOT NULL DEFAULT 0.00 AFTER mesai_yemek_adedi;

-- 3) Tek seferlik taziye yemekleri tablosu
CREATE TABLE IF NOT EXISTS taziye_yemekleri (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    musteri_id          INT DEFAULT NULL,
    firma_adi           VARCHAR(150) NOT NULL,
    tarih               DATE NOT NULL,
    adet                INT NOT NULL DEFAULT 0,
    birim_fiyat         DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    toplam_tutar        DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    aciklama            VARCHAR(255) DEFAULT NULL,
    olusturma_tarihi    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_taz_musteri FOREIGN KEY (musteri_id)
        REFERENCES musteriler(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4) Oluşturulan PDF ekstrelerinin geçmişini saklayan tablo
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
    taziye_yemek_adedi      INT NOT NULL DEFAULT 0,
    taziye_yemek_tutari     DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    onceki_bakiye           DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    donem_toplami           DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    alinan_avans            DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    kalan_bakiye            DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    olusturma_tarihi        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ekstre_musteri FOREIGN KEY (musteri_id)
        REFERENCES musteriler(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
