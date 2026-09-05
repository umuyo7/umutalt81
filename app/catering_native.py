"""PHP catering iş akışlarının FastAPI karşılığı; mevcut MariaDB kullanılır."""
import calendar
import hmac
import os
import secrets
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .auth_session import authenticated_user
from .db import get_db
from .models import BusinessType
from . import catering_store
from .catering_accounting import (money, rounded, customer_balance, period, report,
                                  statement_preview, statement_confirmation, total)

router = APIRouter(prefix='/catering-native', include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).parent / 'templates')
CATEGORIES = ['Personel', 'Yakıt / Nakliye', 'Gıda / Malzeme', 'Paketleme',
              'Kira / Fatura', 'Bakım / Onarım', 'Diğer']
NAV = [('index', 'Panel'), ('musteriler', 'Müşteriler'), ('gunluk_giris', 'Günlük Giriş'),
       ('taziye_ekle', 'Taziye Yemeği'), ('calisanlar', 'Çalışanlar / Maaş'),
       ('raporlama', 'Raporlama'), ('giderler', 'Giderler')]


def today():
    return datetime.now(ZoneInfo('Europe/Istanbul')).date()


def prefix():
    value = os.getenv('APP_PREFIX', '').strip('/')
    return '/' + value if value else ''


def address(page='index', query=''):
    return prefix() + '/catering-native/' + page + '.php' + query


def money_text(value):
    return f'{rounded(value):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.') + ' ₺'


templates.env.filters['money'] = money_text
templates.env.filters['sum_money'] = lambda rows, field: total(list(rows), field)
templates.env.filters['latest'] = lambda rows, field: sorted(rows, key=lambda r: (r[field], int(r['id'])), reverse=True)


def text_value(form, key, limit=255, required=False):
    value = str(form.get(key, '')).strip()
    if len(value) > limit or (required and not value):
        raise ValueError(key + ': alan boş veya fazla uzun.')
    return value


def amount(form, key, positive=False, negative=False):
    value = str(form.get(key, '0')).strip().replace(',', '.')
    result = rounded(value)
    if (not negative and result < 0) or (positive and result <= 0) or abs(result) >= Decimal('100000000'):
        raise ValueError(key + ': geçersiz tutar.')
    return result


def integer(form, key, minimum=0):
    result = int(form.get(key, 0))
    if result < minimum or result > 2147483647:
        raise ValueError(key + ': geçersiz sayı.')
    return result


def day(value):
    return date.fromisoformat(str(value))


def customer_fields(form):
    return dict(sirket_ismi=text_value(form, 'sirket_ismi', 150, True),
                sahis_adi=text_value(form, 'sahis_adi', 150), telefon=text_value(form, 'telefon', 20),
                eposta=text_value(form, 'eposta', 150), adres=text_value(form, 'adres', 10000),
                anlasilan_yemek_fiyati=amount(form, 'anlasilan_yemek_fiyati'),
                mesai_yemek_fiyati=amount(form, 'mesai_yemek_fiyati'),
                varsayilan_kisi_sayisi=integer(form, 'varsayilan_kisi_sayisi'),
                devreden_borc=amount(form, 'devreden_borc'),
                faturali_mi=int('faturali_mi' in form), aktif_mi=int('aktif_mi' in form))


def serialized(rows):
    return [{k: (v.isoformat() if isinstance(v, (date, datetime)) else str(v) if v is not None else None)
             for k, v in row.items()} for row in rows]


def accounting_data(store):
    return {name: serialized(store.rows(name)) for name in catering_store.TABLES}


def execute(store, page, form):
    action = form.get('action')
    ident = integer(form, 'id')
    if page == 'musteriler' and action == 'create':
        new = store.insert('musteriler', customer_fields(form))
        return address('musteri_detay', f'?id={new}')
    if page in ('musteriler', 'musteri_detay'):
        store.get('musteriler', ident, lock=True)
        if action == 'update':
            store.update('musteriler', ident, customer_fields(form))
        elif action == 'invoice':
            store.update('musteriler', ident, {'faturali_mi': integer(form, 'faturali_mi') == 1})
        elif action == 'delete':
            # PHP'deki kullanıcı tarafından müşteri silme işlemi. Geçiş işlemi değildir.
            if form.get('confirm') != 'EVET':
                raise ValueError('Müşteri silme onayı gerekli.')
            for name in ('gunluk_yemek_verileri', 'tahsilatlar', 'ekstreler'):
                for row in store.rows(name, musteri_id=ident):
                    store.delete(name, row['id'])
            store.delete('musteriler', ident)
            return address('musteriler')
        elif action == 'payment':
            store.insert('tahsilatlar', dict(musteri_id=ident, tarih=day(form['odeme_tarih']),
                         tutar=amount(form, 'odeme_tutar', positive=True), aciklama=text_value(form, 'aciklama')))
        elif action == 'delete_statement':
            statement = store.get('ekstreler', integer(form, 'ekstre_id'), lock=True)
            if statement['musteri_id'] != ident:
                raise ValueError('Ekstre müşteriye ait değil.')
            store.delete('ekstreler', statement['id'])
        else:
            raise ValueError('Geçersiz müşteri işlemi.')
        return address('musteri_detay', f'?id={ident}')
    if page == 'gunluk_giris' and action == 'save':
        entry_day = day(form['tarih'])
        identifiers = sorted({int(key.split('_')[-1]) for key in form if key.startswith(('adet_', 'mesai_'))})
        for customer_id in identifiers:
            customer = store.get('musteriler', customer_id, lock=True)
            normal, overtime = integer(form, f'adet_{customer_id}'), integer(form, f'mesai_{customer_id}')
            existing = store.rows('gunluk_yemek_verileri', musteri_id=customer_id, tarih=entry_day)
            if not normal and not overtime:
                for row in existing:
                    store.delete('gunluk_yemek_verileri', row['id'])
                continue
            values = dict(musteri_id=customer_id, tarih=entry_day, yemek_adedi=normal, mesai_yemek_adedi=overtime,
                          gunluk_toplam_tutar=normal * money(customer['anlasilan_yemek_fiyati']),
                          mesai_toplam_tutar=overtime * money(customer['mesai_yemek_fiyati']))
            if existing:
                store.update('gunluk_yemek_verileri', existing[0]['id'], values)
            else:
                store.insert('gunluk_yemek_verileri', values)
        return address(page, f'?tarih={entry_day}')
    if page == 'taziye_ekle':
        if action == 'create':
            count, price = integer(form, 'adet', 1), amount(form, 'birim_fiyat')
            store.insert('taziye_yemekleri', dict(firma_adi=text_value(form, 'firma_adi', 150, True),
                         tarih=day(form['tarih']), adet=count, birim_fiyat=price, toplam_tutar=count * price,
                         aciklama=text_value(form, 'aciklama')))
        elif action == 'delete':
            store.delete('taziye_yemekleri', ident)
        else:
            raise ValueError('Geçersiz taziye işlemi.')
        return address(page)
    if page in ('giderler', 'raporlama'):
        entry_day = day(form['tarih'])
        if action == 'create':
            category = form.get('kategori', 'Diğer')
            store.insert('gunluk_giderler', dict(tarih=entry_day, kategori=category if category in CATEGORIES else 'Diğer',
                         aciklama=text_value(form, 'aciklama', 255, True), tutar=amount(form, 'tutar', True)))
        elif action == 'delete':
            store.delete('gunluk_giderler', ident)
        else:
            raise ValueError('Geçersiz gider işlemi.')
        return address(page, f'?tarih={entry_day}')
    if page == 'calisanlar':
        if action == 'create':
            store.insert('calisanlar', dict(ad_soyad=text_value(form, 'ad_soyad', 150, True),
                         gorev=text_value(form, 'gorev', 100), telefon=text_value(form, 'telefon', 20),
                         aylik_maas=amount(form, 'aylik_maas'), aktif=1,
                         ise_giris_tarihi=day(form['ise_giris_tarihi']) if form.get('ise_giris_tarihi') else None))
        elif action == 'status':
            store.update('calisanlar', ident, {'aktif': int(form.get('aktif') == '1')})
        elif action == 'payment':
            employee = store.get('calisanlar', ident, lock=True)
            if not employee['aktif']:
                raise ValueError('Aktif çalışan bulunamadı.')
            store.insert('maas_odemeleri', dict(calisan_id=ident, donem=day(form['donem']), tarih=day(form['tarih']),
                         tutar=amount(form, 'tutar', True), aciklama=text_value(form, 'aciklama')))
        else:
            raise ValueError('Geçersiz çalışan işlemi.')
        return address(page)
    if page == 'ekstre_olustur' and action == 'confirm':
        customer = serialized([store.get('musteriler', ident, lock=True)])[0]
        meals = serialized(store.rows('gunluk_yemek_verileri', musteri_id=ident))
        payments = serialized(store.rows('tahsilatlar', musteri_id=ident))
        preview = statement_preview(customer, meals, payments, form['baslangic'], form['bitis'])
        result = statement_confirmation(preview, amount(form, 'onceki_bakiye', negative=True), amount(form, 'alinan_avans'))
        extra = result.pop('new_payment_amount')
        if extra:
            store.insert('tahsilatlar', dict(musteri_id=ident, tarih=day(form['bitis']), tutar=extra,
                         aciklama='Ekstre oluşturulurken kaydedilen ödeme'))
        result['musteri_id'] = ident
        result['baslama_tarihi'], result['bitis_tarihi'] = day(form['baslangic']), day(form['bitis'])
        new = store.insert('ekstreler', result)
        return address('ekstre_pdf', f'?id={new}')
    raise ValueError('İşlem bulunamadı.')


def view_data(store, page, params):
    selected = day(params.get('tarih', today()))
    data = accounting_data(store)
    result = dict(selected=selected, today=today(), data=data, categories=CATEGORIES, preview=None)
    customers = data['musteriler']
    balances = {c['id']: customer_balance(c, data['gunluk_yemek_verileri'], data['tahsilatlar']) for c in customers}
    result['balances'] = balances
    if page in ('musteri_detay', 'ekstre_olustur'):
        ident = str(int(params.get('id', 0)))
        customer = next((c for c in customers if c['id'] == ident), None)
        if customer is None:
            raise ValueError('Müşteri bulunamadı.')
        result['customer'] = customer
        for name in ('gunluk_yemek_verileri', 'tahsilatlar', 'ekstreler'):
            result[name] = sorted([r for r in data[name] if r['musteri_id'] == ident], key=lambda r: int(r['id']), reverse=True)
        if page == 'ekstre_olustur' and params.get('baslangic') and params.get('bitis'):
            result['preview'] = statement_preview(customer, data['gunluk_yemek_verileri'], data['tahsilatlar'], params['baslangic'], params['bitis'])
    if page == 'gunluk_giris':
        result['daily'] = {r['musteri_id']: r for r in data['gunluk_yemek_verileri'] if r['tarih'] == str(selected)}
    if page in ('index', 'raporlama'):
        start = selected.replace(day=1)
        if page == 'index':
            start = (start.replace(year=start.year - 1, month=12) if start.month == 1 else start.replace(month=start.month - 1))
        end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
        args = [customers, data['gunluk_yemek_verileri'], data['tahsilatlar'], data['taziye_yemekleri'], data['gunluk_giderler']]
        result.update(month_report=report(*args, start, end), daily_report=report(*args, selected, selected),
                      period_start=start, period_end=end, received=total(period(data['tahsilatlar'], start, end), 'tutar'))
        chart = []
        base = today().year * 12 + today().month - 1
        for offset in range(11, -1, -1):
            year, month = divmod(base - offset, 12)
            first = date(year, month + 1, 1)
            last = first.replace(day=calendar.monthrange(year, month + 1)[1])
            chart.append({'month': first.strftime('%m.%Y'), 'revenue': report(*args, first, last)['revenue']})
        result['chart'] = chart
    return result


@router.api_route('/', methods=['GET'])
@router.api_route('/{page}.php', methods=['GET', 'POST'])
async def catering_page(request: Request, page: str = 'index', db: Session = Depends(get_db)):
    if os.getenv('CATERING_NATIVE_ENABLED', 'false').lower() != 'true':
        raise HTTPException(404)
    user = authenticated_user(request, db)
    if user is None:
        return RedirectResponse(prefix() + '/login', status_code=303)
    if user.business_type != BusinessType.CATERING:
        raise HTTPException(403, 'Bu bölüm catering hesabına aittir.')
    allowed = {p for p, _ in NAV} | {'musteri_detay', 'ekstre_olustur', 'ekstre_pdf', 'ekstre_detay_pdf', 'taziye_pdf'}
    if page not in allowed:
        raise HTTPException(404)
    token = request.session.setdefault('csrf_token', secrets.token_urlsafe(32))
    form = await request.form() if request.method == 'POST' else None
    if form is not None and not hmac.compare_digest(token, str(form.get('csrf_token', ''))):
        raise HTTPException(403, 'Geçersiz form isteği.')
    readonly = os.getenv('CATERING_NATIVE_READONLY', 'true').lower() == 'true'
    if form is not None and readonly:
        raise HTTPException(403, 'Kontrol modu açık; kayıt değiştirme kapalı.')
    try:
        with catering_store.transaction() as store:
            if form is not None:
                target = execute(store, page, form)
                response = RedirectResponse(target, status_code=303)
            elif page.endswith('_pdf'):
                from .catering_pdf import build_pdf
                response = build_pdf(store, page, int(request.query_params.get('id', 0)))
            else:
                context = view_data(store, page, request.query_params)
                response = templates.TemplateResponse(request=request, name='catering_native.html',
                    context=dict(context, page=page, user=user, nav=NAV, csrf_token=token, url=address, app_prefix=prefix(), readonly=readonly))
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    response.headers['Cache-Control'] = 'no-store'
    return response
