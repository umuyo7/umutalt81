"""PHP catering hesap kurallarının Decimal karşılığı; veritabanına yazmaz.

Kaynak alan adları geçiş doğrulamasında bilinçli olarak korunur.
Fiyatlar günlük kayıttaki tutarlardan gelir; güncel müşteri fiyatı kullanılmaz.
"""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def money(value):
    try:
        result = Decimal(str(value))
    except (ValueError, InvalidOperation) as exc:
        raise ValueError("Geçersiz parasal değer") from exc
    if not result.is_finite():
        raise ValueError("Parasal değer sonlu olmalı")
    return result


def rounded(value):
    return money(value).quantize(CENT, rounding=ROUND_HALF_UP)


def total(rows, field):
    return sum((money(row[field]) for row in rows), ZERO)


def period(rows, start, end):
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if end < start:
        raise ValueError("Bitiş tarihi başlangıçtan önce olamaz")
    return [row for row in rows if start <= date.fromisoformat(row["tarih"]) <= end]


def customer_rows(customer, rows):
    return [row for row in rows if str(row["musteri_id"]) == str(customer["id"])]


def tax_rate(customer):
    return Decimal("10") if str(customer["faturali_mi"]) == "1" else ZERO


def service_total(meals):
    return total(meals, "gunluk_toplam_tutar") + total(meals, "mesai_toplam_tutar")


def customer_balance(customer, meals, payments, through=None):
    meals, payments = customer_rows(customer, meals), customer_rows(customer, payments)
    if through is not None:
        boundary = date.fromisoformat(str(through))
        meals = [row for row in meals if date.fromisoformat(row["tarih"]) <= boundary]
        payments = [row for row in payments if date.fromisoformat(row["tarih"]) <= boundary]
    net = service_total(meals)
    gross = money(customer["devreden_borc"]) + net * (1 + tax_rate(customer) / 100)
    paid = total(payments, "tutar")
    return {"service": gross, "paid": paid, "balance": gross - paid,
            "receivable": max(ZERO, gross - paid),
            # PHP musteri_detay.php farklı olarak KDV'siz bakiye gösteriyor.
            # Bu fark geçiş incelemesinde görünür kalır; sessizce düzeltilmez.
            "legacy_detail_balance": money(customer["devreden_borc"]) + net - paid}


def statement_preview(customer, meals, payments, start, end):
    meals, payments = customer_rows(customer, meals), customer_rows(customer, payments)
    selected = period(meals, start, end)
    advances = total(period(payments, start, end), "tutar")
    boundary = date.fromisoformat(str(start))
    previous_meals = [r for r in meals if date.fromisoformat(r["tarih"]) < boundary]
    previous_payments = [r for r in payments if date.fromisoformat(r["tarih"]) < boundary]
    previous = money(customer["devreden_borc"]) + service_total(previous_meals) * (1 + tax_rate(customer) / 100) - total(previous_payments, "tutar")
    normal_count = sum(int(r["yemek_adedi"]) for r in selected)
    overtime_count = sum(int(r["mesai_yemek_adedi"]) for r in selected)
    normal = total(selected, "gunluk_toplam_tutar")
    overtime = total(selected, "mesai_toplam_tutar")
    tax = rounded((normal + overtime) * tax_rate(customer) / 100)
    return {
        "musteri_id": customer["id"], "baslama_tarihi": str(start), "bitis_tarihi": str(end),
        "gun_sayisi": 0, "kisi_sayisi": 0,
        "normal_yemek_adedi": normal_count, "normal_yemek_tutari": normal,
        "normal_yemek_fiyati": normal / normal_count if normal_count else money(customer["anlasilan_yemek_fiyati"]),
        "mesai_yemek_adedi": overtime_count, "mesai_yemek_tutari": overtime,
        "mesai_yemek_fiyati": overtime / overtime_count if overtime_count else money(customer["mesai_yemek_fiyati"]),
        "fazla_yemek_adedi": 0, "fazla_yemek_fiyati": ZERO, "fazla_yemek_tutari": ZERO,
        "onceki_bakiye": previous, "donem_ara_toplami": normal + overtime,
        "kdv_orani": tax_rate(customer), "kdv_tutari": tax,
        "donem_toplami": normal + overtime + tax, "alinan_avans": advances,
        "kalan_bakiye": previous + normal + overtime + tax - advances,
    }


def statement_confirmation(preview, previous_balance, requested_advance):
    """Ekstre üretiminde eklenecek tahsilat farkını da döndürür.

Çağıran servis aynı müşteriyi transaction içinde kilitleyip önizlemeyi
yeniden hesaplamalı; bu fonksiyon tek başına ödeme kaydetmez.
"""
    result = dict(preview)
    recorded = money(preview["alinan_avans"])
    requested = rounded(requested_advance)
    if requested < 0:
        raise ValueError("Avans negatif olamaz")
    result["onceki_bakiye"] = rounded(previous_balance)
    result["alinan_avans"] = max(recorded, requested)
    result["new_payment_amount"] = max(ZERO, requested - recorded)
    result["kalan_bakiye"] = result["onceki_bakiye"] + result["donem_toplami"] - result["alinan_avans"]
    return result


def report(customers, meals, payments, condolences, expenses, start, end):
    by_id = {str(row["id"]): row for row in customers}
    selected = period(meals, start, end)
    revenue = sum((service_total([r]) * (1 + tax_rate(by_id[str(r["musteri_id"])]) / 100) for r in selected), ZERO)
    revenue += total(period(condolences, start, end), "toplam_tutar")
    costs = total(period(expenses, start, end), "tutar")
    return {"revenue": revenue, "expenses": costs, "net": revenue - costs,
            "meal_count": sum(int(r["yemek_adedi"]) for r in selected),
            "overtime_count": sum(int(r["mesai_yemek_adedi"]) for r in selected),
            "receivables": sum((customer_balance(c, meals, payments, end)["receivable"] for c in customers), ZERO)}
