"""InfinityFree JSON dışa aktarımını PostgreSQL'e tek seferde taşır."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import func

from .db import Base, SessionLocal, engine
from .models import (
    BusinessType,
    CondolenceMeal,
    Customer,
    DailyMeal,
    Employee,
    Expense,
    LegacyImport,
    LegacyStatement,
    CateringPayment,
    RestaurantRevenue,
    SalaryPayment,
    User,
)


def as_decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def as_bool(value) -> bool:
    return str(value or "0").strip().lower() in {"1", "true", "yes", "evet"}


def as_date(value) -> date | None:
    raw = str(value or "").strip()[:10]
    if not raw or raw == "0000-00-00":
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def table(data: dict, name: str) -> list[dict]:
    rows = data.get("tables", {}).get(name, [])
    if not isinstance(rows, list):
        raise ValueError(f"{name} tablosu beklenen liste biçiminde değil.")
    return rows


def import_file(path: Path, force: bool = False) -> dict[str, int]:
    raw = path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw.decode("utf-8-sig"))
    if data.get("format") != "bereket-infinityfree-v1":
        raise ValueError("Bu dosya Bereket InfinityFree dışa aktarımı değil.")

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.query(LegacyImport).filter(LegacyImport.source_sha256 == source_hash).first():
            raise RuntimeError("Bu dışa aktarım daha önce içeri alınmış; tekrar işlem yapılmadı.")

        catering_username = os.environ["CATERING_USERNAME"].strip().lower()
        restaurant_username = os.environ["RESTAURANT_USERNAME"].strip().lower()
        catering_user = db.query(User).filter(User.username == catering_username, User.business_type == BusinessType.CATERING).first()
        restaurant_user = db.query(User).filter(User.username == restaurant_username, User.business_type == BusinessType.RESTAURANT).first()
        if not catering_user or not restaurant_user:
            raise RuntimeError("Önce uygulamayı başlatın; catering ve restoran kullanıcıları oluşturulamadı.")

        managed_models = (Customer, DailyMeal, CateringPayment, CondolenceMeal, RestaurantRevenue, Expense, Employee, SalaryPayment, LegacyStatement)
        existing = sum(db.query(func.count(model.id)).scalar() or 0 for model in managed_models)
        if existing and not force:
            raise RuntimeError("Hedefte işletme verisi zaten var. Yanlışlıkla çoğaltmamak için aktarım durduruldu.")

        counts: dict[str, int] = {}
        customer_ids: dict[int, int] = {}
        employee_ids: dict[int, int] = {}

        for row in table(data, "musteriler"):
            customer = Customer(
                user_id=catering_user.id,
                company_name=str(row.get("sirket_ismi") or "İsimsiz müşteri")[:160],
                contact_name=str(row.get("sahis_adi") or "")[:160],
                phone=str(row.get("telefon") or "")[:32],
                email=str(row.get("eposta") or "")[:190],
                address=str(row.get("adres") or ""),
                meal_price=as_decimal(row.get("anlasilan_yemek_fiyati")),
                overtime_price=as_decimal(row.get("mesai_yemek_fiyati")),
                default_people=max(0, as_int(row.get("varsayilan_kisi_sayisi"))),
                invoice_customer=as_bool(row.get("faturali_mi")),
                carried_debt=as_decimal(row.get("devreden_borc")),
                active=as_bool(row.get("aktif_mi")),
            )
            db.add(customer)
            db.flush()
            customer_ids[as_int(row.get("id"))] = customer.id
        counts["musteriler"] = len(customer_ids)

        seen_meals: set[tuple[int, date]] = set()
        for row in table(data, "gunluk_yemek_verileri"):
            customer_id = customer_ids.get(as_int(row.get("musteri_id")))
            entry_date = as_date(row.get("tarih"))
            key = (customer_id or 0, entry_date) if entry_date else None
            if not customer_id or not entry_date or key in seen_meals:
                continue
            seen_meals.add(key)
            db.add(DailyMeal(
                customer_id=customer_id,
                entry_date=entry_date,
                meal_count=max(0, as_int(row.get("yemek_adedi"))),
                overtime_count=max(0, as_int(row.get("mesai_yemek_adedi"))),
            ))
        counts["gunluk_yemek_verileri"] = len(seen_meals)

        payment_count = 0
        for row in table(data, "tahsilatlar"):
            customer_id = customer_ids.get(as_int(row.get("musteri_id")))
            payment_date = as_date(row.get("tarih"))
            if not customer_id or not payment_date:
                continue
            db.add(CateringPayment(customer_id=customer_id, payment_date=payment_date, amount=as_decimal(row.get("tutar")), note=str(row.get("aciklama") or "")[:255]))
            payment_count += 1
        counts["tahsilatlar"] = payment_count

        condolence_count = 0
        for row in table(data, "taziye_yemekleri"):
            entry_date = as_date(row.get("tarih"))
            if not entry_date:
                continue
            db.add(CondolenceMeal(
                user_id=catering_user.id,
                company_name=str(row.get("firma_adi") or "")[:160],
                entry_date=entry_date,
                quantity=max(0, as_int(row.get("adet"))),
                unit_price=as_decimal(row.get("birim_fiyat")),
                total_amount=as_decimal(row.get("toplam_tutar")),
                note=str(row.get("aciklama") or ""),
            ))
            condolence_count += 1
        counts["taziye_yemekleri"] = condolence_count

        expense_count = 0
        for row in table(data, "gunluk_giderler"):
            expense_date = as_date(row.get("tarih"))
            if not expense_date:
                continue
            db.add(Expense(
                user_id=restaurant_user.id,
                expense_date=expense_date,
                category=str(row.get("kategori") or "Diğer")[:100],
                description=str(row.get("aciklama") or "")[:255],
                amount=as_decimal(row.get("tutar")),
            ))
            expense_count += 1
        counts["gunluk_giderler"] = expense_count

        for row in table(data, "calisanlar"):
            employee = Employee(
                user_id=restaurant_user.id,
                name=str(row.get("ad_soyad") or "İsimsiz çalışan")[:160],
                role=str(row.get("gorev") or "")[:120],
                phone=str(row.get("telefon") or "")[:32],
                monthly_salary=as_decimal(row.get("aylik_maas")),
                start_date=as_date(row.get("ise_giris_tarihi")),
                active=as_bool(row.get("aktif")),
            )
            db.add(employee)
            db.flush()
            employee_ids[as_int(row.get("id"))] = employee.id
        counts["calisanlar"] = len(employee_ids)

        salary_count = 0
        for row in table(data, "maas_odemeleri"):
            employee_id = employee_ids.get(as_int(row.get("calisan_id")))
            payment_date = as_date(row.get("tarih"))
            if not employee_id or not payment_date:
                continue
            db.add(SalaryPayment(
                employee_id=employee_id,
                payment_date=payment_date,
                period=str(row.get("donem") or "")[:30],
                amount=as_decimal(row.get("tutar")),
                note=str(row.get("aciklama") or "")[:255],
            ))
            salary_count += 1
        counts["maas_odemeleri"] = salary_count

        statement_count = 0
        for row in table(data, "ekstreler"):
            legacy_customer_id = as_int(row.get("musteri_id"))
            db.add(LegacyStatement(
                user_id=catering_user.id,
                customer_id=customer_ids.get(legacy_customer_id),
                legacy_id=as_int(row.get("id")) or None,
                payload=row,
            ))
            statement_count += 1
        counts["ekstreler"] = statement_count

        db.add(LegacyImport(source_sha256=source_hash, counts=counts))
        db.commit()
        return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="InfinityFree verisini Bereket PostgreSQL veritabanına aktarır.")
    parser.add_argument("json_file", type=Path)
    parser.add_argument("--force", action="store_true", help="Hedefte veri varken de aktar (çoğaltma riski vardır).")
    args = parser.parse_args()
    counts = import_file(args.json_file, force=args.force)
    print("Aktarım tamamlandı:")
    for name, count in counts.items():
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
