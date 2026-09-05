"""Kaynak PHP şemasıyla uçtan uca test; yalnız geçici SQLite verisi kullanır."""
import os
import re
import tempfile
from pathlib import Path
from contextlib import contextmanager

from sqlalchemy import create_engine, MetaData, Table, Column, Integer, Numeric, String, Text, Date, DateTime, text


def source_schema(engine):
    # Test şeması doğrudan teslim edilmiş PHP database.sql tanımından çıkarılır.
    sql = (Path(__file__).resolve().parents[1] / 'catering-php/database.sql').read_text(encoding='utf-8-sig')
    metadata = MetaData()
    tables = {}
    for name, body in re.findall(r'CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\) ENGINE=', sql, re.S):
        columns = []
        for line in body.splitlines():
            match = re.match(r'\s*(\w+)\s+(INT|TINYINT|VARCHAR|DECIMAL|TEXT|DATE|DATETIME)\b(\([^)]*\))?(.*)', line)
            if not match:
                continue
            field, kind, params, suffix = match.groups()
            params = [int(n) for n in re.findall(r'\d+', params or '')]
            datatype = {'INT': Integer, 'TINYINT': Integer, 'VARCHAR': String, 'DECIMAL': Numeric,
                        'TEXT': Text, 'DATE': Date, 'DATETIME': DateTime}[kind]
            kwargs = dict(primary_key=field=='id', nullable='NOT NULL' not in suffix and field!='id')
            default = re.search(r"DEFAULT\s+('[^']*'|CURRENT_TIMESTAMP|NULL|[0-9.]+)",suffix)
            if default:
                kwargs['server_default'] = text(default.group(1))
            columns.append(Column(field,datatype(*params) if params and kind not in ('INT','TINYINT') else datatype(),**kwargs))
        tables[name] = Table(name,metadata,*columns)
    metadata.create_all(engine)
    return tables


def run():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        os.environ.update(DATABASE_URL='sqlite:///' + (directory/'identity.db').as_posix(), APP_ENV='test',
                          APP_PREFIX='', COOKIE_HTTPS_ONLY='true', SESSION_SECRET='s'*48,
                          CATERING_SSO_SECRET='c'*48, CATERING_USERNAME='catering-native-test',
                          CATERING_PASSWORD='Catering-Native-Test-123!', RESTAURANT_USERNAME='restaurant-native-test',
                          RESTAURANT_PASSWORD='Restaurant-Native-Test-123!', CATERING_NATIVE_ENABLED='true', CATERING_BACKEND='native', CATERING_NATIVE_READONLY='false')
        from fastapi.testclient import TestClient
        from app.main import app
        from app import catering_store
        from app.catering_store import Store
        source_engine = create_engine('sqlite:///' + (directory/'source.db').as_posix(),connect_args={'check_same_thread':False})
        tables = source_schema(source_engine)
        from app.catering_check import REQUIRED
        for name, required in REQUIRED.items():
            assert set(required.split()) <= set(tables[name].c.keys())
        @contextmanager
        def transaction():
            with source_engine.begin() as connection:
                yield Store(connection,tables)
        catering_store.transaction = transaction
        with TestClient(app,base_url='https://testserver') as client:
            login = client.get('/login')
            token = re.search(r'const token = "([^"]+)"',login.text).group(1)
            client.post('/login',data={'username':'catering-native-test','password':'Catering-Native-Test-123!','csrf_token':token})
            home = client.get('/catering-native/')
            assert home.status_code==200,home.text
            token = re.search(r'name="csrf_token" value="([^"]+)"',home.text).group(1)
            def post(page, values):
                response = client.post('/catering-native/'+page+'.php',data=dict(values,csrf_token=token),follow_redirects=False)
                assert response.status_code==303,(page,response.status_code,response.text)
                return response
            c = dict(sirket_ismi='Örnek Şirket & <Test>',sahis_adi='Çağrı',telefon='05551234567',eposta='',adres='İstanbul',
                     anlasilan_yemek_fiyati='50',mesai_yemek_fiyati='70',varsayilan_kisi_sayisi='3',
                     devreden_borc='100',faturali_mi='on',aktif_mi='on')
            created = post('musteriler',dict(c,action='create'))
            ident = created.headers['location'].split('id=')[1]
            assert client.get(created.headers['location']).status_code==200
            post('gunluk_giris',{'action':'save','tarih':'2026-09-01','adet_'+ident:'3','mesai_'+ident:'1'})
            post('musteri_detay',dict(c,id=ident,action='update',anlasilan_yemek_fiyati='999'))
            post('musteri_detay',dict(id=ident,action='payment',odeme_tarih='2026-09-01',odeme_tutar='100',aciklama='Avans'))
            preview = client.get(f'/catering-native/ekstre_olustur.php?id={ident}&baslangic=2026-09-01&bitis=2026-09-30')
            assert preview.status_code==200,preview.text
            assert '220,00' not in preview.text or '242,00' in preview.text
            confirm = dict(action='confirm',id=ident,baslangic='2026-09-01',bitis='2026-09-30',onceki_bakiye='100',alinan_avans='150')
            created_statement = post('ekstre_olustur',confirm)
            post('ekstre_olustur',confirm)
            with transaction() as store:
                assert sum(r['tutar'] for r in store.rows('tahsilatlar'))==150
                assert store.rows('gunluk_yemek_verileri')[0]['gunluk_toplam_tutar']==150
                statement = store.rows('ekstreler')[0]
                assert statement['kalan_bakiye']==192 and statement['kdv_tutari']==22,statement
                assert statement['normal_yemek_fiyati']==50
            post('taziye_ekle',dict(action='create',firma_adi='Taziye Örneği',tarih='2026-09-01',adet='100',birim_fiyat='80',aciklama='Örnek açıklama'))
            post('giderler',dict(action='create',tarih='2026-09-01',kategori='Yakıt / Nakliye',aciklama='Yakıt',tutar='250'))
            post('calisanlar',dict(action='create',ad_soyad='Örnek Çalışan',gorev='Aşçı',telefon='',aylik_maas='35000',ise_giris_tarihi='2026-01-01'))
            post('calisanlar',dict(action='payment',id='1',donem='2026-09-01',tarih='2026-09-05',tutar='1000',aciklama='Avans'))
            pages = ['index','musteriler','gunluk_giris','taziye_ekle','calisanlar','giderler','raporlama']
            output = Path(os.getenv('CATERING_QA_DIR',str(directory/'pdfs')))
            output.mkdir(parents=True,exist_ok=True)
            for page in pages:
                response = client.get('/catering-native/'+page+'.php?tarih=2026-09-01')
                assert response.status_code==200,(page,response.text)
                assert 'Cache-Control' in response.headers
                (output/(page+'.html')).write_text(response.text,encoding='utf-8')
            detail = client.get(f'/catering-native/musteri_detay.php?id={ident}')
            assert '&lt;Test&gt;' in detail.text and '<Test>' not in detail.text
            pdfs = [('ekstre_pdf',1),('ekstre_detay_pdf',1),('taziye_pdf',1)]
            for kind, key in pdfs:
                response = client.get(f'/catering-native/{kind}.php?id={key}')
                assert response.status_code==200 and response.content.startswith(b'%PDF'),response.text[:300]
                (output/(kind+'.pdf')).write_bytes(response.content)
            # Çok sayfalı günlük detay ve uzun metin kontrolü.
            with transaction() as store:
                from datetime import date,timedelta
                for offset in range(1,85):
                    store.insert('gunluk_yemek_verileri',dict(musteri_id=int(ident),tarih=date(2026,9,1)+timedelta(days=offset),
                        yemek_adedi=3,mesai_yemek_adedi=1,gunluk_toplam_tutar=150,mesai_toplam_tutar=70))
                store.update('ekstreler',1,dict(bitis_tarihi=date(2026,12,1)))
            response = client.get('/catering-native/ekstre_detay_pdf.php?id=1')
            assert response.status_code==200
            (output/'detay_multipage.pdf').write_bytes(response.content)
            invalid = client.post('/catering-native/musteriler.php',data=dict(c,action='create',csrf_token='wrong'))
            assert invalid.status_code==403
            os.environ['CATERING_NATIVE_READONLY']='true'
            assert client.post('/catering-native/musteriler.php',data=dict(c,action='create',csrf_token=token)).status_code==403
            assert client.get('/catering-native/').status_code==200
            os.environ['CATERING_NATIVE_READONLY']='false'
            # Başarısız form transaction'ı önceki değişiklikleri de geri alır.
            before = None
            with transaction() as store:
                before = len(store.rows('gunluk_yemek_verileri'))
            failed = client.post('/catering-native/gunluk_giris.php',data={'csrf_token':token,'action':'save',
                'tarih':'2026-12-31','adet_'+ident:'1','mesai_'+ident:'0','adet_999999':'1'})
            assert failed.status_code==422
            with transaction() as store:
                assert len(store.rows('gunluk_yemek_verileri'))==before
            post('calisanlar',dict(action='status',id=1,aktif='0'))
            rejected = client.post('/catering-native/calisanlar.php',data=dict(csrf_token=token,action='payment',id=1,
                donem='2026-09-01',tarih='2026-09-05',tutar='1000',aciklama='İkinci ödeme'))
            assert rejected.status_code==422
            post('musteriler',dict(action='invoice',id=ident,faturali_mi='0'))
            post('gunluk_giris',{'action':'save','tarih':'2026-09-01','adet_'+ident:'0','mesai_'+ident:'0'})
            post('musteri_detay',dict(action='delete_statement',id=ident,ekstre_id=2))
            post('taziye_ekle',dict(action='delete',id=1))
            post('giderler',dict(action='delete',id=1,tarih='2026-09-01'))
            with transaction() as store:
                assert len(store.rows('gunluk_yemek_verileri'))==before-1
                assert len(store.rows('ekstreler'))==1
                assert len(store.rows('tahsilatlar'))==2
                assert len(store.rows('taziye_yemekleri'))==0
                assert len(store.rows('gunluk_giderler'))==0
            post('musteriler',dict(action='delete',id=ident,confirm='EVET'))
            with transaction() as store:
                for name in ('musteriler','gunluk_yemek_verileri','tahsilatlar','ekstreler'):
                    assert len(store.rows(name))==0
            # Garson/restoran kimliği catering ekranına giremez.
            client.post('/logout',data={'csrf_token':token})
            login = client.get('/login')
            token = re.search(r'const token = "([^"]+)"',login.text).group(1)
            client.post('/login',data={'username':'restaurant-native-test','password':'Restaurant-Native-Test-123!','csrf_token':token})
            assert client.get('/catering-native/').status_code==403
            os.environ['CATERING_NATIVE_ENABLED']='false'
            assert client.get('/catering-native/').status_code==404
        source_engine.dispose()
        from app.db import engine
        engine.dispose()
    print('catering-native-flow-ok')


if __name__=='__main__':
    run()
