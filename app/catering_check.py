"""Canlı catering şemasını ve kayıt sayılarını yalnız SELECT ile kontrol eder."""
import json
import sys
from sqlalchemy import select, func
from .catering_store import source

REQUIRED = {
    'musteriler': 'id sirket_ismi sahis_adi telefon eposta adres anlasilan_yemek_fiyati mesai_yemek_fiyati varsayilan_kisi_sayisi faturali_mi devreden_borc aktif_mi kayit_tarihi',
    'gunluk_yemek_verileri': 'id musteri_id tarih yemek_adedi mesai_yemek_adedi gunluk_toplam_tutar mesai_toplam_tutar',
    'taziye_yemekleri': 'id firma_adi tarih adet birim_fiyat toplam_tutar aciklama',
    'tahsilatlar': 'id musteri_id tarih tutar aciklama',
    'gunluk_giderler': 'id tarih kategori aciklama tutar',
    'calisanlar': 'id ad_soyad gorev telefon aylik_maas ise_giris_tarihi aktif',
    'maas_odemeleri': 'id calisan_id donem tarih tutar aciklama',
    'ekstreler': 'id musteri_id baslama_tarihi bitis_tarihi gun_sayisi kisi_sayisi normal_yemek_adedi normal_yemek_fiyati normal_yemek_tutari mesai_yemek_adedi mesai_yemek_fiyati mesai_yemek_tutari fazla_yemek_adedi fazla_yemek_fiyati fazla_yemek_tutari onceki_bakiye donem_ara_toplami kdv_orani kdv_tutari donem_toplami alinan_avans kalan_bakiye',
}


def main():
    try:
        engine, tables = source()
        result = {'ok': True, 'tables': {}}
        with engine.connect() as connection:
            for name, required in REQUIRED.items():
                table = tables[name]
                missing = sorted(set(required.split()) - set(table.c.keys()))
                count = connection.scalar(select(func.count()).select_from(table))
                result['tables'][name] = {'rows': count, 'missing_columns': missing}
                result['ok'] &= not missing
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['ok'] else 1
    except Exception as error:
        # SQLAlchemy bağlantı hataları DSN içerebilir; ham hata basılmaz.
        print('Catering bağlantı/şema kontrolü başarısız: ' + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
