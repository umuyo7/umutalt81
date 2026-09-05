-- =========================================================
-- DÜZELTME: taziye_yemekleri tablosunu müşteri bağlantısından
-- tamamen ayırma
-- =========================================================
-- Taziye yemeği HER ZAMAN tek seferliktir, kayıtlı bir müşteriye
-- ASLA bağlanmaz ve hiçbir müşterinin ekstre/PDF'ine dahil edilmez.
--
-- Bu tabloda henüz veri olmadığı için (ekran görüntüsünde "Henüz
-- taziye yemeği kaydı yok" görünüyordu) en temiz ve güvenli yöntem
-- tabloyu doğru yapıyla yeniden oluşturmaktır. Eğer bu betiği
-- çalıştırdığınız ana kadar taziye_ekle.php üzerinden birkaç kayıt
-- girdiyseniz, DROP TABLE satırından önce phpMyAdmin > taziye_yemekleri
-- > Dışa Aktar ile önce yedek alın.
--
-- phpMyAdmin > veritabanınız > SQL sekmesine yapıştırıp çalıştırın.
-- =========================================================

DROP TABLE IF EXISTS taziye_yemekleri;

CREATE TABLE taziye_yemekleri (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    firma_adi           VARCHAR(150) NOT NULL,
    tarih               DATE NOT NULL,
    adet                INT NOT NULL DEFAULT 0,
    birim_fiyat         DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    toplam_tutar        DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    aciklama            VARCHAR(255) DEFAULT NULL,
    olusturma_tarihi    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ekstreler tablosunda taziye ile ilgili sütunlar varsa (artık
-- kullanılmıyorlar) kaldırılır. Bu sütunlar hiç oluşmadıysa MySQL
-- hata verir; o durumda bu iki satırı çalıştırmadan atlayabilirsiniz.
-- ALTER TABLE ekstreler DROP COLUMN taziye_yemek_adedi;
-- ALTER TABLE ekstreler DROP COLUMN taziye_yemek_tutari;
