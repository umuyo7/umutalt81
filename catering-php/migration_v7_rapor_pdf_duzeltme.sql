-- Bereket Catering rapor/PDF veri uyumluluk duzeltmesi
-- Eski InfinityFree ekstrelerinde sifir kalan ara toplami,
-- kayitli yemek tutarlarindan yeniden olusturur.

START TRANSACTION;

UPDATE ekstreler
SET donem_ara_toplami = ROUND(
    COALESCE(normal_yemek_tutari, 0) +
    COALESCE(mesai_yemek_tutari, 0) +
    COALESCE(fazla_yemek_tutari, 0),
    2
)
WHERE ABS(COALESCE(donem_ara_toplami, 0)) < 0.005
  AND ABS(
      COALESCE(normal_yemek_tutari, 0) +
      COALESCE(mesai_yemek_tutari, 0) +
      COALESCE(fazla_yemek_tutari, 0)
  ) >= 0.005;

COMMIT;
