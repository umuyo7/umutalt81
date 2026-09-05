-- =========================================================
-- MIGRATION v3 — Çalışan ve Maaş Gideri Takibi
-- =========================================================
-- Mevcut veritabanı kullananlar bu dosyanın tamamını phpMyAdmin
-- > SQL ekranında bir kez çalıştırmalıdır.

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
