from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import User
from .pos_models import (
    Category,
    Check,
    CheckItem,
    Payment,
    PaymentStatus,
    Product,
    Role,
    ServiceSession,
    UserRole,
)


ZERO = Decimal("0.00")


def _money(value: Decimal) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def operation_report(db: Session, date_from: date, date_to: date) -> dict:
    if date_to < date_from or (date_to - date_from).days > 366:
        raise ValueError("Rapor tarih aralığı geçersiz veya 367 günden uzun.")
    start = datetime.combine(date_from, time.min)
    end = datetime.combine(date_to + timedelta(days=1), time.min)
    closed_rows = db.execute(
        select(Check, ServiceSession, User)
        .join(ServiceSession, ServiceSession.id == Check.service_session_id)
        .join(User, User.id == ServiceSession.primary_waiter_id)
        .where(Check.closed_at >= start, Check.closed_at < end)
        .order_by(Check.closed_at)
    ).all()
    check_ids = [check.id for check, _, _ in closed_rows]
    items = db.execute(
        select(CheckItem, Product, Category)
        .outerjoin(Product, Product.id == CheckItem.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(CheckItem.check_id.in_(check_ids))
    ).all() if check_ids else []
    payments = db.scalars(
        select(Payment).where(
            Payment.check_id.in_(check_ids),
            Payment.status == PaymentStatus.COMPLETED,
            Payment.created_at >= start,
            Payment.created_at < end,
        )
    ).all() if check_ids else []
    payment_actor_ids = {row.created_by_user_id for row in payments}
    actor_roles: dict[int, set[str]] = defaultdict(set)
    if payment_actor_ids:
        for user_id, role_code in db.execute(
            select(UserRole.user_id, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id.in_(payment_actor_ids))
        ):
            actor_roles[user_id].add(role_code)

    gross = sum((Decimal(check.subtotal) for check, _, _ in closed_rows), ZERO)
    discount = sum((Decimal(check.discount_total) for check, _, _ in closed_rows), ZERO)
    comp = sum((Decimal(check.comp_total) for check, _, _ in closed_rows), ZERO)
    net = sum((Decimal(check.final_total) for check, _, _ in closed_rows), ZERO)
    guests = sum(service.guest_count for _, service, _ in closed_rows)
    cancelled = sum((Decimal(item.line_total) for item, _, _ in items if item.is_cancelled), ZERO)
    durations = [
        Decimal((check.closed_at - service.opened_at).total_seconds()) / Decimal(60)
        for check, service, _ in closed_rows if check.closed_at and service.opened_at
    ]

    waiter_data: dict[int, dict] = {}
    for check, service, waiter in closed_rows:
        row = waiter_data.setdefault(waiter.id, {"name": waiter.name, "services": 0, "guests": 0, "net": ZERO, "discount": ZERO, "comp": ZERO, "cancelled": ZERO})
        row["services"] += 1
        row["guests"] += service.guest_count
        row["net"] += Decimal(check.final_total)
        row["discount"] += Decimal(check.discount_total)
        row["comp"] += Decimal(check.comp_total)
    waiter_by_check = {check.id: waiter.id for check, _, waiter in closed_rows}
    for item, _, _ in items:
        if item.is_cancelled and item.check_id in waiter_by_check:
            waiter_data[waiter_by_check[item.check_id]]["cancelled"] += Decimal(item.line_total)

    product_data: dict[str, dict] = {}
    category_data: dict[str, dict] = {}
    for item, product, category in items:
        if item.is_cancelled:
            continue
        product_name = item.product_name_snapshot
        category_name = category.name if category else "Arşiv/Diğer"
        for bucket, key in ((product_data, product_name), (category_data, category_name)):
            row = bucket.setdefault(key, {"name": key, "quantity": Decimal("0"), "gross": ZERO, "comp": ZERO})
            row["quantity"] += Decimal(item.quantity)
            row["gross"] += Decimal(item.line_total)
            if item.is_comp:
                row["comp"] += Decimal(item.line_total)

    hourly: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for check, _, _ in closed_rows:
        if check.closed_at:
            hourly[check.closed_at.hour] += Decimal(check.final_total)
    payment_methods: dict[str, Decimal] = defaultdict(lambda: ZERO)
    payment_context = {"before_request": ZERO, "after_request": ZERO, "manager": ZERO, "cashier": ZERO, "other": ZERO}
    for payment in payments:
        payment_methods[payment.payment_method.value] += Decimal(payment.amount)
        if payment.check_status_snapshot == "CHECK_REQUESTED":
            payment_context["after_request"] += Decimal(payment.amount)
        else:
            payment_context["before_request"] += Decimal(payment.amount)
        roles = actor_roles.get(payment.created_by_user_id, set())
        if roles & {"manager", "admin"}:
            payment_context["manager"] += Decimal(payment.amount)
        elif "cashier" in roles:
            payment_context["cashier"] += Decimal(payment.amount)
        else:
            payment_context["other"] += Decimal(payment.amount)

    def finalize_waiter(row: dict) -> dict:
        row = dict(row)
        row["per_guest"] = _money(row["net"] / Decimal(row["guests"])) if row["guests"] else ZERO
        row["average_table"] = _money(row["net"] / Decimal(row["services"])) if row["services"] else ZERO
        for key in ("net", "discount", "comp", "cancelled"):
            row[key] = _money(row[key])
        return row

    def finalize_sales(rows: dict[str, dict]) -> list[dict]:
        result = []
        for row in rows.values():
            current = dict(row)
            current["quantity"] = Decimal(current["quantity"]).quantize(Decimal("0.001"))
            current["gross"] = _money(current["gross"])
            current["comp"] = _money(current["comp"])
            current["net"] = _money(current["gross"] - current["comp"])
            result.append(current)
        return sorted(result, key=lambda row: (row["net"], row["quantity"]), reverse=True)

    check_count = len(closed_rows)
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "summary": {
            "gross": _money(gross), "net": _money(net), "discount": _money(discount), "comp": _money(comp),
            "cancelled": _money(cancelled), "guests": guests, "per_guest": _money(net / Decimal(guests)) if guests else ZERO,
            "average_table": _money(net / Decimal(check_count)) if check_count else ZERO, "checks": check_count,
            "average_service_minutes": int((sum(durations, Decimal(0)) / Decimal(len(durations))).quantize(Decimal("1"))) if durations else 0,
        },
        "payments": {key: _money(value) for key, value in sorted(payment_methods.items())},
        "payment_context": {key: _money(value) for key, value in payment_context.items()},
        "waiters": sorted((finalize_waiter(row) for row in waiter_data.values()), key=lambda row: row["net"], reverse=True),
        "products": finalize_sales(product_data),
        "categories": finalize_sales(category_data),
        "hourly": [{"hour": hour, "net": _money(hourly.get(hour, ZERO))} for hour in range(24) if hourly.get(hour, ZERO)],
    }
