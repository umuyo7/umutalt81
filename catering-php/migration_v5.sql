-- =========================================================
-- MIGRATION v5 — Faturalı müşteriler için KDV alanları
-- =========================================================
-- Mevcut veritabanında bir kez çalıştırın.

ALTER TABLE ekstreler
    ADD COLUMN donem_ara_toplami DECIMAL(10,2) NOT NULL DEFAULT 0.00 AFTER onceki_bakiye,
    ADD COLUMN kdv_orani DECIMAL(5,2) NOT NULL DEFAULT 0.00 AFTER donem_ara_toplami,
    ADD COLUMN kdv_tutari DECIMAL(10,2) NOT NULL DEFAULT 0.00 AFTER kdv_orani;
