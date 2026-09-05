"""Mevcut catering şemasına erişim; CREATE/DROP veya otomatik migration yok."""
import os
from contextlib import contextmanager
from functools import lru_cache
from sqlalchemy import MetaData, Table, create_engine, select
from sqlalchemy.engine import URL

TABLES = ('musteriler', 'gunluk_yemek_verileri', 'taziye_yemekleri', 'tahsilatlar',
          'gunluk_giderler', 'calisanlar', 'maas_odemeleri', 'ekstreler')


@lru_cache(maxsize=1)
def source():
    url = URL.create('mysql+pymysql', username=os.environ['CATERING_DB_USER'],
                     password=os.environ['CATERING_DB_PASSWORD'],
                     host=os.environ['CATERING_DB_HOST'], database=os.environ['CATERING_DB_NAME'],
                     query={'charset': 'utf8mb4'})
    engine = create_engine(url, pool_pre_ping=True, isolation_level='REPEATABLE READ')
    metadata = MetaData()
    tables = {name: Table(name, metadata, autoload_with=engine) for name in TABLES}
    return engine, tables


class Store:
    def __init__(self, connection, tables):
        self.connection, self.tables = connection, tables

    def rows(self, name, **filters):
        table = self.tables[name]
        query = select(table)
        for key, value in filters.items():
            query = query.where(table.c[key] == value)
        return [dict(r) for r in self.connection.execute(query.order_by(table.c.id)).mappings()]

    def get(self, name, ident, lock=False):
        table = self.tables[name]
        query = select(table).where(table.c.id == ident)
        if lock:
            query = query.with_for_update()
        row = self.connection.execute(query).mappings().first()
        if row is None:
            raise ValueError('Kayıt bulunamadı.')
        return dict(row)

    def insert(self, name, values):
        result = self.connection.execute(self.tables[name].insert().values(**values))
        return result.inserted_primary_key[0]

    def update(self, name, ident, values):
        table = self.tables[name]
        self.get(name, ident, lock=True)
        self.connection.execute(table.update().where(table.c.id == ident).values(**values))

    def delete(self, name, ident):
        table = self.tables[name]
        self.get(name, ident, lock=True)
        self.connection.execute(table.delete().where(table.c.id == ident))


@contextmanager
def transaction():
    engine, tables = source()
    with engine.begin() as connection:
        yield Store(connection, tables)
