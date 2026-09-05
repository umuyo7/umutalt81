"""Salt okunur snapshot kontrolü. SQL çalıştırmaz, veritabanı açmaz."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from .catering_accounting import money, ZERO

EXPECTED = {
    'musteriler', 'gunluk_yemek_verileri', 'taziye_yemekleri', 'tahsilatlar',
    'gunluk_giderler', 'calisanlar', 'maas_odemeleri', 'ekstreler',
}
RELATIONS = {
    'gunluk_yemek_verileri': ('musteri_id', 'musteriler'),
    'tahsilatlar': ('musteri_id', 'musteriler'),
    'ekstreler': ('musteri_id', 'musteriler'),
    'maas_odemeleri': ('calisan_id', 'calisanlar'),
}


def validate(data):
    if data.get('format') != 'bereket-catering-snapshot-v1':
        raise ValueError('Beklenen snapshot biçimi değil')
    tables = data.get('tables')
    if not isinstance(tables, dict) or set(tables) - EXPECTED:
        raise ValueError('Tablo listesi geçersiz')
    errors, warnings, summary, ids = [], [], {}, {}
    missing = sorted(EXPECTED - set(tables))
    if missing:
        errors.append('Eksik tablolar: ' + ', '.join(missing))
    if sorted(data.get('missing_tables', [])) != missing:
        errors.append('Eksik tablo bildirimi tutarsız')
    if data.get('additional_tables'):
        errors.append('Ek tablolar inceleme gerektiriyor: ' + ', '.join(data['additional_tables']))
    for name, entry in tables.items():
        rows = entry.get('rows')
        columns = entry.get('columns')
        if not isinstance(rows, list) or not isinstance(columns, list):
            raise ValueError('Tablo satır/sütun biçimi geçersiz: ' + name)
        fields = {column['Field'] for column in columns}
        if 'id' not in fields or len(fields) != len(columns):
            raise ValueError('Sütun listesi geçersiz: ' + name)
        numeric = {c['Field'] for c in columns if re.match(r'^(decimal|numeric|int|bigint|smallint|tinyint|mediumint)\b', c['Type'], re.I)}
        if set(entry.get('totals', {})) != numeric:
            errors.append(name + ': sayısal kontrol toplamları eksik/fazla')
        if entry.get('row_count') != len(rows):
            errors.append(name + ': satır sayısı eşleşmiyor')
        ids[name] = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError('Eksik/fazla satır alanı: ' + name)
            # Ondalık değerler float üzerinden geçmemeli.
            if any(value is not None and not isinstance(value, str) for value in row.values()):
                raise ValueError('Alanlar string veya null olmalı: ' + name)
            ident = row['id']
            if ident is None or not re.fullmatch(r'[1-9][0-9]*', ident):
                raise ValueError('Geçersiz satır kimliği: ' + name)
            if ident in ids[name]:
                errors.append(name + ': yinelenen kimlik')
            ids[name].add(ident)
        totals = {}
        for field in numeric:
            computed = sum((money(r[field]) for r in rows if r[field] is not None), ZERO)
            expected = entry.get('totals', {}).get(field)
            if expected is None or computed != money(expected):
                errors.append(name + '.' + field + ': SQL toplamı ile satırlar eşleşmiyor')
            totals[field] = str(computed)
        summary[name] = {'rows': len(rows), 'columns': sorted(fields), 'totals': totals}
    for child, (field, parent) in RELATIONS.items():
        if child in tables and parent in tables:
            if any(r.get(field) not in ids[parent] for r in tables[child]['rows']):
                errors.append(child + ': bağlı ana kayıt bulunamadı')
    seen = set()
    for row in tables.get('gunluk_yemek_verileri', {}).get('rows', []):
        key = (row.get('musteri_id'), row.get('tarih'))
        if key in seen:
            errors.append('Aynı müşteri/tarih için birden fazla günlük yemek kaydı')
        seen.add(key)
    warnings.append('Bu kontrol aktarım yapmaz; hedef kayıt ve bakiye mutabakatı ayrıca gereklidir.')
    return {'valid': not errors, 'errors': errors, 'warnings': warnings, 'tables': summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    raw = args.snapshot.read_bytes()
    result = validate(json.loads(raw.decode('utf-8-sig')))
    result['source_sha256'] = hashlib.sha256(raw).hexdigest()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['valid'] else 1)


if __name__ == '__main__':
    main()
