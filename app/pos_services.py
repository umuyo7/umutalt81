from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import User
from .permissions import permission_decision, require_permission
from .request_context import current_request_context
from .pos_models import (
    AuditLog,
    Category,
    Check,
    CheckMerge,
    CheckSplit,
    CheckSplitMember,
    CheckItem,
    CheckStatus,
    Discount,
    DiscountStatus,
    DiscountType,
    ForceCloseAdjustment,
    IdempotencyRecord,
    OutboxEvent,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Product,
    RestaurantTable,
    ServiceSession,
    ServiceStatus,
    ServiceWaiterTransfer,
    Shift,
    TableSection,
    TableTransfer,
)


MONEY = Decimal("0.01")
ACTIVE_SERVICE_STATUSES = (
    ServiceStatus.OPEN,
    ServiceStatus.CHECK_REQUESTED,
    ServiceStatus.PAYMENT_IN_PROGRESS,
)


class PosError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def active_check_request(service: ServiceSession) -> bool:
    return service.check_requested_at is not None and (
        service.check_request_cancelled_at is None
        or service.check_request_cancelled_at < service.check_requested_at
    )


def _audit(
    db: Session,
    actor_user_id: int,
    action: str,
    entity_type: str,
    entity_id: int | str,
    *,
    old_value: dict | None = None,
    new_value: dict | None = None,
    reason: str | None = None,
) -> None:
    context = current_request_context()
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            session_id=context.get("session_id"),
            request_id=context.get("request_id"),
        )
    )


def _event(db: Session, event_type: str, aggregate_type: str, aggregate_id: int | str, payload: dict) -> None:
    db.add(
        OutboxEvent(
            id=str(uuid4()),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=str(aggregate_id),
            payload=payload,
        )
    )


def _locked_check(db: Session, check_id: int) -> Check:
    check = db.scalar(select(Check).where(Check.id == check_id).with_for_update())
    if check is None:
        raise PosError("CHECK_NOT_FOUND", "Adisyon bulunamadı.", 404)
    return check


def _service_for_check(db: Session, check: Check, lock: bool = False) -> ServiceSession:
    statement = select(ServiceSession).where(ServiceSession.id == check.service_session_id)
    if lock:
        statement = statement.with_for_update()
    service = db.scalar(statement)
    if service is None:
        raise PosError("SERVICE_NOT_FOUND", "Adisyona bağlı servis bulunamadı.", 409)
    return service


def recalculate_check(db: Session, check: Check) -> Check:
    items = db.scalars(select(CheckItem).where(CheckItem.check_id == check.id)).all()
    gross = sum((money(row.line_total) for row in items if not row.is_cancelled), Decimal("0.00"))
    comp = sum((money(row.line_total) for row in items if not row.is_cancelled and row.is_comp), Decimal("0.00"))
    discount_base = max(Decimal("0.00"), gross - comp)

    discounts = db.scalars(
        select(Discount).where(Discount.check_id == check.id, Discount.status == DiscountStatus.ACTIVE)
    ).all()
    discount_total = Decimal("0.00")
    for row in discounts:
        if row.discount_type == DiscountType.PERCENTAGE:
            calculated = money(discount_base * Decimal(row.value) / Decimal("100"))
        else:
            calculated = money(row.value)
        row.calculated_amount = min(calculated, max(Decimal("0.00"), discount_base - discount_total))
        discount_total += row.calculated_amount

    final_total = max(Decimal("0.00"), money(gross - comp - discount_total))
    paid = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.check_id == check.id,
            Payment.status == PaymentStatus.COMPLETED,
        )
    )
    paid_total = money(Decimal(paid or 0))
    check.subtotal = money(gross)
    check.comp_total = money(comp)
    check.discount_total = money(discount_total)
    check.final_total = final_total
    check.paid_total = paid_total
    check.balance_due = max(Decimal("0.00"), money(final_total - paid_total))
    if check.status != CheckStatus.CLOSED:
        if check.balance_due == 0 and check.final_total > 0:
            check.status = CheckStatus.PAID
        elif check.paid_total > 0:
            check.status = CheckStatus.PARTIALLY_PAID
        else:
            check.status = CheckStatus.OPEN
    check.version += 1
    return check


def open_service(db: Session, actor_user_id: int, table_id: int, guest_count: int) -> tuple[ServiceSession, Check]:
    require_permission(db, actor_user_id, "service.open")
    if not 1 <= guest_count <= 50:
        raise PosError("INVALID_GUEST_COUNT", "Kişi sayısı 1 ile 50 arasında olmalıdır.", 422)
    table = db.scalar(select(RestaurantTable).where(RestaurantTable.id == table_id).with_for_update())
    if table is None or not table.is_active:
        raise PosError("TABLE_NOT_FOUND", "Masa bulunamadı veya kullanım dışı.", 404)
    active = db.scalar(
        select(ServiceSession).where(
            ServiceSession.table_id == table_id,
            ServiceSession.operational_status.in_(ACTIVE_SERVICE_STATUSES),
        )
    )
    if active is not None:
        raise PosError("TABLE_ALREADY_OPEN", "Bu masada aktif bir servis bulunuyor.", 409)
    service = ServiceSession(
        table_id=table.id,
        primary_waiter_id=actor_user_id,
        guest_count=guest_count,
        operational_status=ServiceStatus.OPEN,
        opened_by_user_id=actor_user_id,
    )
    db.add(service)
    try:
        db.flush()
    except IntegrityError as exc:
        raise PosError("TABLE_ALREADY_OPEN", "Bu masa başka bir kullanıcı tarafından az önce açıldı.", 409) from exc
    check = Check(
        check_number=f"BS-{datetime.now():%y%m%d}-{service.id:06d}",
        service_session_id=service.id,
        status=CheckStatus.OPEN,
    )
    db.add(check)
    db.flush()
    _audit(
        db,
        actor_user_id,
        "SERVICE_OPEN",
        "service_session",
        service.id,
        new_value={"table_id": table.id, "guest_count": guest_count, "check_id": check.id},
    )
    _event(db, "service.opened", "service_session", service.id, {"table_id": table.id, "check_id": check.id})
    return service, check


def add_item(
    db: Session,
    actor_user_id: int,
    check_id: int,
    product_id: int,
    quantity: Decimal = Decimal("1"),
    note: str | None = None,
) -> CheckItem:
    require_permission(db, actor_user_id, "order.add_item")
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise PosError("INVALID_QUANTITY", "Ürün adedi sıfırdan büyük olmalıdır.", 422)
    check = _locked_check(db, check_id)
    if check.status == CheckStatus.CLOSED:
        raise PosError("CHECK_CLOSED", "Kapalı adisyona ürün eklenemez.", 409)
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise PosError("PRODUCT_NOT_FOUND", "Ürün bulunamadı veya satışta değil.", 404)
    row = CheckItem(
        check_id=check.id,
        product_id=product.id,
        product_name_snapshot=product.name,
        unit_price=money(product.price),
        tax_rate_snapshot=Decimal(product.tax_rate),
        quantity=quantity,
        line_total=money(Decimal(product.price) * quantity),
        note=(note or "").strip() or None,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    recalculate_check(db, check)
    _audit(db, actor_user_id, "ITEM_ADD", "check_item", row.id, new_value={"check_id": check.id, "product_id": product.id, "quantity": str(quantity), "unit_price": str(row.unit_price)})
    _event(db, "check.updated", "check", check.id, {"check_id": check.id})
    return row


def send_to_kitchen(
    db: Session, actor_user_id: int, table_id: int
) -> tuple[Check, ServiceSession, list[CheckItem], datetime]:
    require_permission(db, actor_user_id, "order.add_item")
    service = db.scalar(
        select(ServiceSession).where(
            ServiceSession.table_id == table_id,
            ServiceSession.operational_status.in_(ACTIVE_SERVICE_STATUSES),
        ).with_for_update()
    )
    if service is None:
        raise PosError("SERVICE_NOT_FOUND", "Masada açık servis bulunamadı.", 404)
    check = db.scalar(select(Check).where(Check.service_session_id == service.id).with_for_update())
    if check is None or check.status == CheckStatus.CLOSED:
        raise PosError("CHECK_NOT_FOUND", "Açık adisyon bulunamadı.", 404)
    items = db.scalars(
        select(CheckItem).where(
            CheckItem.check_id == check.id,
            CheckItem.is_cancelled.is_(False),
            CheckItem.sent_to_kitchen_at.is_(None),
        ).order_by(CheckItem.created_at, CheckItem.id).with_for_update()
    ).all()
    if not items:
        raise PosError("NO_UNSENT_ITEMS", "Mutfağa gönderilmemiş yeni ürün bulunmuyor.", 409)
    sent_at = datetime.utcnow()
    for item in items:
        item.sent_to_kitchen_at = sent_at
        item.sent_to_kitchen_by_user_id = actor_user_id
    _audit(db, actor_user_id, "KITCHEN_SEND", "check", check.id, new_value={"table_id": table_id, "item_ids": [item.id for item in items]})
    _event(db, "kitchen.sent", "check", check.id, {"table_id": table_id, "item_ids": [item.id for item in items]})
    return check, service, items, sent_at


def update_item_quantity(db: Session, actor_user_id: int, item_id: int, quantity: Decimal) -> CheckItem:
    require_permission(db, actor_user_id, "order.change_quantity")
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise PosError("INVALID_QUANTITY", "Ürün adedi sıfırdan büyük olmalıdır.", 422)
    row = db.scalar(select(CheckItem).where(CheckItem.id == item_id).with_for_update())
    if row is None or row.is_cancelled:
        raise PosError("ITEM_NOT_FOUND", "Adisyon kalemi bulunamadı.", 404)
    check = _locked_check(db, row.check_id)
    if check.status == CheckStatus.CLOSED:
        raise PosError("CHECK_CLOSED", "Kapalı adisyon değiştirilemez.", 409)
    old = {"quantity": str(row.quantity), "line_total": str(row.line_total)}
    row.quantity = quantity
    row.line_total = money(Decimal(row.unit_price) * quantity)
    row.updated_by_user_id = actor_user_id
    row.updated_at = datetime.utcnow()
    row.version += 1
    recalculate_check(db, check)
    _audit(db, actor_user_id, "ITEM_UPDATE", "check_item", row.id, old_value=old, new_value={"quantity": str(quantity), "line_total": str(row.line_total)})
    _event(db, "check.updated", "check", check.id, {"check_id": check.id})
    return row


def override_item_price(db: Session, actor_user_id: int, item_id: int, unit_price: Decimal, reason: str) -> CheckItem:
    require_permission(db, actor_user_id, "order.change_price")
    unit_price = money(unit_price)
    if unit_price < 0 or not reason.strip():
        raise PosError("INVALID_PRICE_OVERRIDE", "Yeni fiyat ve düzeltme nedeni zorunludur.", 422)
    row = db.scalar(select(CheckItem).where(CheckItem.id == item_id).with_for_update())
    if row is None or row.is_cancelled:
        raise PosError("ITEM_NOT_FOUND", "Aktif adisyon kalemi bulunamadı.", 404)
    check = _locked_check(db, row.check_id)
    if check.status == CheckStatus.CLOSED:
        raise PosError("CHECK_CLOSED", "Kapalı adisyon değiştirilemez.", 409)
    old_price = money(row.unit_price)
    if not row.price_override:
        row.original_unit_price = old_price
    row.unit_price = unit_price
    row.line_total = money(unit_price * Decimal(row.quantity))
    row.price_override = True
    row.price_override_reason = reason.strip()
    row.price_overridden_by_user_id = actor_user_id
    row.updated_by_user_id = actor_user_id
    row.updated_at = datetime.utcnow()
    row.version += 1
    recalculate_check(db, check)
    _audit(db, actor_user_id, "PRICE_OVERRIDE", "check_item", row.id, old_value={"unit_price": str(old_price)}, new_value={"unit_price": str(unit_price)}, reason=reason.strip())
    _event(db, "check.updated", "check", check.id, {"check_id": check.id})
    return row


def cancel_item(db: Session, actor_user_id: int, item_id: int, reason: str) -> CheckItem:
    require_permission(db, actor_user_id, "order.cancel_item")
    if not reason.strip():
        raise PosError("REASON_REQUIRED", "Ürün iptal nedeni zorunludur.", 422)
    row = db.scalar(select(CheckItem).where(CheckItem.id == item_id).with_for_update())
    if row is None or row.is_cancelled:
        raise PosError("ITEM_NOT_FOUND", "Aktif adisyon kalemi bulunamadı.", 404)
    check = _locked_check(db, row.check_id)
    if check.status == CheckStatus.CLOSED:
        raise PosError("CHECK_CLOSED", "Kapalı adisyon değiştirilemez.", 409)
    row.is_cancelled = True
    row.cancel_reason = reason.strip()
    row.cancelled_by_user_id = actor_user_id
    row.cancelled_at = datetime.utcnow()
    row.version += 1
    recalculate_check(db, check)
    _audit(db, actor_user_id, "ITEM_CANCEL", "check_item", row.id, old_value={"is_cancelled": False}, new_value={"is_cancelled": True}, reason=reason.strip())
    _event(db, "check.updated", "check", check.id, {"check_id": check.id})
    return row


def comp_item(db: Session, actor_user_id: int, item_id: int, reason: str) -> CheckItem:
    require_permission(db, actor_user_id, "order.comp_item")
    if not reason.strip():
        raise PosError("REASON_REQUIRED", "İkram nedeni zorunludur.", 422)
    row = db.scalar(select(CheckItem).where(CheckItem.id == item_id).with_for_update())
    if row is None or row.is_cancelled:
        raise PosError("ITEM_NOT_FOUND", "Aktif adisyon kalemi bulunamadı.", 404)
    check = _locked_check(db, row.check_id)
    row.is_comp = True
    row.comp_reason = reason.strip()
    row.comp_by_user_id = actor_user_id
    row.comp_at = datetime.utcnow()
    row.version += 1
    recalculate_check(db, check)
    _audit(db, actor_user_id, "ITEM_COMP", "check_item", row.id, new_value={"is_comp": True, "amount": str(row.line_total)}, reason=reason.strip())
    _event(db, "check.updated", "check", check.id, {"check_id": check.id})
    return row


def apply_discount(db: Session, actor_user_id: int, check_id: int, discount_type: DiscountType, value: Decimal, reason: str) -> Discount:
    require_permission(db, actor_user_id, "discount.apply")
    value = money(value)
    if value <= 0 or not reason.strip():
        raise PosError("INVALID_DISCOUNT", "İndirim değeri ve nedeni zorunludur.", 422)
    if discount_type == DiscountType.PERCENTAGE:
        if value > 100:
            raise PosError("INVALID_DISCOUNT", "İndirim yüzdesi 100'ü aşamaz.", 422)
        limit = permission_decision(db, actor_user_id, "discount.max_percent").limit or Decimal("0")
        if value > limit and not permission_decision(db, actor_user_id, "discount.override_limit").allowed:
            raise PosError("DISCOUNT_LIMIT_EXCEEDED", f"İndirim limitiniz %{limit}.", 403)
    check = _locked_check(db, check_id)
    if check.status == CheckStatus.CLOSED:
        raise PosError("CHECK_CLOSED", "Kapalı adisyona indirim uygulanamaz.", 409)
    row = Discount(
        check_id=check.id,
        discount_type=discount_type,
        value=value,
        calculated_amount=Decimal("0.00"),
        reason=reason.strip(),
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    recalculate_check(db, check)
    _audit(db, actor_user_id, "DISCOUNT_ADD", "discount", row.id, new_value={"type": discount_type.value, "value": str(value), "amount": str(row.calculated_amount)}, reason=reason.strip())
    _event(db, "check.updated", "check", check.id, {"check_id": check.id})
    return row


def remove_discount(db: Session, actor_user_id: int, discount_id: int, reason: str) -> Discount:
    require_permission(db, actor_user_id, "discount.remove")
    if not reason.strip():
        raise PosError("REASON_REQUIRED", "İndirim kaldırma nedeni zorunludur.", 422)
    row = db.scalar(select(Discount).where(Discount.id == discount_id).with_for_update())
    if row is None or row.status != DiscountStatus.ACTIVE:
        raise PosError("DISCOUNT_NOT_ACTIVE", "Aktif indirim bulunamadı.", 404)
    check = _locked_check(db, row.check_id)
    row.status = DiscountStatus.REMOVED
    row.removed_by_user_id = actor_user_id
    row.removed_at = datetime.utcnow()
    row.removal_reason = reason.strip()
    recalculate_check(db, check)
    _audit(db, actor_user_id, "DISCOUNT_REMOVE", "discount", row.id, old_value={"status": "ACTIVE"}, new_value={"status": "REMOVED"}, reason=reason.strip())
    _event(db, "check.updated", "check", check.id, {"check_id": check.id})
    return row


def request_check(db: Session, actor_user_id: int, check_id: int) -> ServiceSession:
    require_permission(db, actor_user_id, "check.request")
    check = _locked_check(db, check_id)
    if check.status == CheckStatus.CLOSED:
        raise PosError("CHECK_CLOSED", "Kapalı adisyon için hesap talebi oluşturulamaz.", 409)
    service = _service_for_check(db, check, lock=True)
    service.check_requested_at = datetime.utcnow()
    if check.paid_total > 0:
        service.operational_status = ServiceStatus.PAYMENT_IN_PROGRESS
    else:
        service.operational_status = ServiceStatus.CHECK_REQUESTED
    service.version += 1
    _audit(db, actor_user_id, "CHECK_REQUEST", "check", check.id, new_value={"requested": True})
    _event(db, "check.requested", "check", check.id, {"table_id": service.table_id})
    return service


def cancel_check_request(db: Session, actor_user_id: int, check_id: int) -> ServiceSession:
    require_permission(db, actor_user_id, "check.cancel_request")
    check = _locked_check(db, check_id)
    service = _service_for_check(db, check, lock=True)
    service.check_request_cancelled_at = datetime.utcnow()
    service.operational_status = ServiceStatus.PAYMENT_IN_PROGRESS if check.paid_total > 0 else ServiceStatus.OPEN
    service.version += 1
    _audit(db, actor_user_id, "CHECK_REQUEST_CANCEL", "check", check.id, new_value={"requested": False})
    _event(db, "check.request_cancelled", "check", check.id, {"table_id": service.table_id})
    return service


def payment_request_hash(check_id: int, method: PaymentMethod, amount: Decimal, external_reference: str | None) -> str:
    payload = json.dumps(
        {"check_id": check_id, "method": method.value, "amount": str(money(amount)), "external_reference": external_reference or ""},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_payment(
    db: Session,
    actor_user_id: int,
    check_id: int,
    method: PaymentMethod,
    amount: Decimal,
    idempotency_key: str,
    external_reference: str | None = None,
    notes: str | None = None,
) -> tuple[Payment, bool, str | None]:
    require_permission(db, actor_user_id, "payment.create")
    if not idempotency_key or len(idempotency_key) > 120:
        raise PosError("IDEMPOTENCY_KEY_REQUIRED", "Geçerli Idempotency-Key zorunludur.", 422)
    amount = money(amount)
    if amount <= 0:
        raise PosError("INVALID_PAYMENT_AMOUNT", "Ödeme tutarı sıfırdan büyük olmalıdır.", 422)
    request_hash = payment_request_hash(check_id, method, amount, external_reference)
    # Aynı adisyondaki idempotency kontrolü ve bakiye hesabı tek sıra üzerinde ilerler.
    check = _locked_check(db, check_id)
    existing = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == "payment.create",
            IdempotencyRecord.actor_user_id == actor_user_id,
            IdempotencyRecord.idempotency_key == idempotency_key,
        ).with_for_update()
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise PosError("IDEMPOTENCY_KEY_REUSED", "Bu işlem anahtarı farklı bir ödeme için kullanılmış.", 409)
        if not existing.resource_id:
            raise PosError("IDEMPOTENCY_IN_PROGRESS", "Ödeme işlemi halen tamamlanıyor.", 409)
        payment = db.get(Payment, int(existing.resource_id))
        if payment is None:
            raise PosError("IDEMPOTENCY_RESOURCE_MISSING", "Önceki ödeme sonucu bulunamadı.", 409)
        return payment, True, (existing.response_body_json or {}).get("notice")

    if check.status == CheckStatus.CLOSED:
        raise PosError("CHECK_CLOSED", "Kapalı adisyona ödeme alınamaz.", 409)
    service = _service_for_check(db, check, lock=True)
    without_request = not active_check_request(service)
    if without_request:
        require_permission(db, actor_user_id, "payment.create_without_check_request")
    recalculate_check(db, check)
    if check.final_total <= 0:
        raise PosError("CHECK_TOTAL_EMPTY", "Ödeme alınabilecek bir adisyon tutarı yok.", 409)
    if check.balance_due <= 0:
        raise PosError("CHECK_ALREADY_PAID", "Adisyon bakiyesi zaten tamamlanmış.", 409)
    if amount > check.balance_due:
        raise PosError("PAYMENT_EXCEEDS_BALANCE", f"Ödeme kalan {check.balance_due:.2f} ₺ bakiyeyi aşamaz.", 422)

    shift = db.scalar(select(Shift).where(Shift.closed_at.is_(None)).order_by(Shift.opened_at.desc()).with_for_update())
    payment = Payment(
        check_id=check.id,
        shift_id=shift.id if shift else None,
        payment_method=method,
        amount=amount,
        status=PaymentStatus.COMPLETED,
        check_status_snapshot=service.operational_status.value,
        created_by_user_id=actor_user_id,
        external_reference=(external_reference or "").strip() or None,
        notes=(notes or "").strip() or None,
    )
    db.add(payment)
    db.flush()
    recalculate_check(db, check)
    service.operational_status = ServiceStatus.PAYMENT_IN_PROGRESS
    service.version += 1
    notice = "Ödeme, hesap talebi oluşturulmadan alındı." if without_request else None
    db.add(
        IdempotencyRecord(
            scope="payment.create",
            actor_user_id=actor_user_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            resource_type="payment",
            resource_id=str(payment.id),
            response_status=201,
            response_body_json={"payment_id": payment.id, "check_id": check.id, "notice": notice},
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
    )
    action = "PAYMENT_CREATE_WITHOUT_CHECK_REQUEST" if without_request else "PAYMENT_CREATE"
    _audit(db, actor_user_id, action, "payment", payment.id, new_value={"check_id": check.id, "method": method.value, "amount": str(amount)})
    _event(db, "payment.created", "payment", payment.id, {"check_id": check.id, "table_id": service.table_id})
    return payment, False, notice


def close_check(db: Session, actor_user_id: int, check_id: int) -> Check:
    require_permission(db, actor_user_id, "payment.close_check")
    check = _locked_check(db, check_id)
    service = _service_for_check(db, check, lock=True)
    recalculate_check(db, check)
    if check.balance_due != 0 or check.final_total <= 0:
        raise PosError("CHECK_BALANCE_REMAINING", "Adisyon yalnız bakiye tamamlandığında kapatılabilir.", 409)
    now = datetime.utcnow()
    check.status = CheckStatus.CLOSED
    check.closed_at = now
    check.closed_by_user_id = actor_user_id
    service.operational_status = ServiceStatus.CLOSED
    service.closed_at = now
    service.closed_by_user_id = actor_user_id
    check.version += 1
    service.version += 1
    _audit(db, actor_user_id, "SERVICE_CLOSE", "check", check.id, new_value={"final_total": str(check.final_total), "paid_total": str(check.paid_total)})
    _event(db, "service.closed", "service_session", service.id, {"check_id": check.id, "table_id": service.table_id})
    return check


def force_close_check(db: Session, actor_user_id: int, check_id: int, reason: str) -> Check:
    require_permission(db, actor_user_id, "payment.force_close")
    if not reason.strip():
        raise PosError("REASON_REQUIRED", "Zorla kapatma nedeni zorunludur.", 422)
    check = _locked_check(db, check_id)
    service = _service_for_check(db, check, lock=True)
    recalculate_check(db, check)
    adjustment = ForceCloseAdjustment(
        check_id=check.id,
        expected_total=check.final_total,
        paid_total=check.paid_total,
        difference_amount=money(check.final_total - check.paid_total),
        reason=reason.strip(),
        created_by_user_id=actor_user_id,
    )
    db.add(adjustment)
    now = datetime.utcnow()
    check.status = CheckStatus.CLOSED
    check.closed_at = now
    check.closed_by_user_id = actor_user_id
    service.operational_status = ServiceStatus.CLOSED
    service.closed_at = now
    service.closed_by_user_id = actor_user_id
    _audit(db, actor_user_id, "FORCE_CLOSE", "check", check.id, new_value={"difference": str(adjustment.difference_amount)}, reason=reason.strip())
    _event(db, "service.closed", "service_session", service.id, {"check_id": check.id, "table_id": service.table_id, "forced": True})
    return check


def reopen_check(db: Session, actor_user_id: int, check_id: int, reason: str) -> Check:
    require_permission(db, actor_user_id, "check.reopen")
    if not reason.strip():
        raise PosError("REASON_REQUIRED", "Yeniden açma nedeni zorunludur.", 422)
    check = _locked_check(db, check_id)
    if check.status != CheckStatus.CLOSED:
        raise PosError("CHECK_NOT_CLOSED", "Yalnız kapalı adisyon yeniden açılabilir.", 409)
    service = _service_for_check(db, check, lock=True)
    now = datetime.utcnow()
    check.reopened_at = now
    check.reopened_by_user_id = actor_user_id
    check.closed_at = None
    check.closed_by_user_id = None
    service.closed_at = None
    service.closed_by_user_id = None
    recalculate_check(db, check)
    service.operational_status = ServiceStatus.PAYMENT_IN_PROGRESS if check.paid_total > 0 else (ServiceStatus.CHECK_REQUESTED if active_check_request(service) else ServiceStatus.OPEN)
    _audit(db, actor_user_id, "SERVICE_REOPEN", "check", check.id, new_value={"status": check.status.value}, reason=reason.strip())
    _event(db, "check.reopened", "check", check.id, {"table_id": service.table_id})
    return check


def reverse_payment(db: Session, actor_user_id: int, payment_id: int, reason: str) -> Payment:
    require_permission(db, actor_user_id, "payment.reverse")
    if not reason.strip():
        raise PosError("REASON_REQUIRED", "Ödeme reversal nedeni zorunludur.", 422)
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None or payment.status != PaymentStatus.COMPLETED:
        raise PosError("PAYMENT_NOT_ACTIVE", "Aktif ödeme bulunamadı.", 404)
    if payment.shift_id and db.scalar(select(Shift.closed_at).where(Shift.id == payment.shift_id)) is not None:
        raise PosError("SHIFT_CLOSED", "Kapanmış vardiyadaki ödeme değiştirilemez.", 409)
    check = _locked_check(db, payment.check_id)
    if check.status == CheckStatus.CLOSED:
        raise PosError("REOPEN_REQUIRED", "Ödemeyi reverse etmeden önce adisyonu yeniden açın.", 409)
    service = _service_for_check(db, check, lock=True)
    payment.status = PaymentStatus.REVERSED
    payment.reversed_by_user_id = actor_user_id
    payment.reversed_at = datetime.utcnow()
    payment.reversal_reason = reason.strip()
    recalculate_check(db, check)
    service.operational_status = ServiceStatus.PAYMENT_IN_PROGRESS if check.paid_total > 0 else (ServiceStatus.CHECK_REQUESTED if active_check_request(service) else ServiceStatus.OPEN)
    _audit(db, actor_user_id, "PAYMENT_REVERSE", "payment", payment.id, old_value={"status": "COMPLETED"}, new_value={"status": "REVERSED"}, reason=reason.strip())
    _event(db, "payment.reversed", "payment", payment.id, {"check_id": check.id, "table_id": service.table_id})
    return payment


def change_payment_method(db: Session, actor_user_id: int, payment_id: int, method: PaymentMethod, reason: str) -> Payment:
    require_permission(db, actor_user_id, "payment.change_method")
    if not reason.strip():
        raise PosError("REASON_REQUIRED", "Ödeme yöntemi düzeltme nedeni zorunludur.", 422)
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None or payment.status != PaymentStatus.COMPLETED:
        raise PosError("PAYMENT_NOT_ACTIVE", "Aktif ödeme bulunamadı.", 404)
    if payment.shift_id and db.scalar(select(Shift.closed_at).where(Shift.id == payment.shift_id)) is not None:
        raise PosError("SHIFT_CLOSED", "Kapanmış vardiyadaki ödeme değiştirilemez.", 409)
    check = _locked_check(db, payment.check_id)
    if check.status == CheckStatus.CLOSED:
        raise PosError("REOPEN_REQUIRED", "Ödeme yöntemini düzeltmeden önce adisyonu yeniden açın.", 409)
    old_method = payment.payment_method
    payment.status = PaymentStatus.REVERSED
    payment.reversed_by_user_id = actor_user_id
    payment.reversed_at = datetime.utcnow()
    payment.reversal_reason = reason.strip()
    replacement = Payment(
        check_id=payment.check_id,
        shift_id=payment.shift_id,
        payment_method=method,
        amount=payment.amount,
        status=PaymentStatus.COMPLETED,
        check_status_snapshot=payment.check_status_snapshot,
        created_by_user_id=actor_user_id,
        reverses_payment_id=payment.id,
        notes=f"Ödeme yöntemi düzeltmesi: {reason.strip()}",
    )
    db.add(replacement)
    db.flush()
    recalculate_check(db, check)
    _audit(db, actor_user_id, "PAYMENT_METHOD_CHANGE", "payment", payment.id, old_value={"method": old_method.value}, new_value={"method": method.value, "replacement_payment_id": replacement.id}, reason=reason.strip())
    _event(db, "payment.reversed", "payment", payment.id, {"check_id": check.id})
    _event(db, "payment.created", "payment", replacement.id, {"check_id": check.id})
    return replacement


def open_shift(db: Session, actor_user_id: int, opening_cash_amount: Decimal) -> Shift:
    require_permission(db, actor_user_id, "shift.open")
    opening_cash_amount = money(opening_cash_amount)
    if opening_cash_amount < 0:
        raise PosError("INVALID_OPENING_CASH", "Açılış nakdi sıfırdan küçük olamaz.", 422)
    if db.scalar(select(Shift.id).where(Shift.closed_at.is_(None))) is not None:
        raise PosError("SHIFT_ALREADY_OPEN", "Zaten açık bir kasa vardiyası var.", 409)
    shift = Shift(opened_by_user_id=actor_user_id, opening_cash_amount=opening_cash_amount)
    db.add(shift)
    db.flush()
    _audit(db, actor_user_id, "SHIFT_OPEN", "shift", shift.id, new_value={"opening_cash_amount": str(opening_cash_amount)})
    return shift


def shift_payment_totals(db: Session, shift_id: int) -> dict[PaymentMethod, Decimal]:
    totals = {method: Decimal("0.00") for method in PaymentMethod}
    rows = db.execute(
        select(Payment.payment_method, func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.shift_id == shift_id, Payment.status == PaymentStatus.COMPLETED)
        .group_by(Payment.payment_method)
    ).all()
    for method, amount in rows:
        totals[method] = money(Decimal(amount))
    return totals


def shift_summary(db: Session, shift: Shift) -> dict:
    totals = shift_payment_totals(db, shift.id)
    expected = money(Decimal(shift.opening_cash_amount) + totals[PaymentMethod.CASH])
    actual = money(shift.closing_cash_amount) if shift.closing_cash_amount is not None else None
    difference = money(actual - expected) if actual is not None else None
    return {"totals": totals, "expected_cash_amount": expected, "closing_cash_amount": actual, "cash_difference": difference}


def close_shift(db: Session, actor_user_id: int, closing_cash_amount: Decimal, note: str | None = None) -> tuple[Shift, dict]:
    require_permission(db, actor_user_id, "shift.close")
    closing_cash_amount = money(closing_cash_amount)
    if closing_cash_amount < 0:
        raise PosError("INVALID_CLOSING_CASH", "Sayılan nakit sıfırdan küçük olamaz.", 422)
    shift = db.scalar(select(Shift).where(Shift.closed_at.is_(None)).order_by(Shift.opened_at.desc()).with_for_update())
    if shift is None:
        raise PosError("SHIFT_NOT_OPEN", "Kapatılacak açık vardiya bulunmuyor.", 409)
    if db.scalar(select(Check.id).where(Check.status != CheckStatus.CLOSED).limit(1)) is not None:
        raise PosError("OPEN_CHECKS_EXIST", "Vardiya kapanmadan önce tüm açık adisyonlar kapatılmalıdır.", 409)
    summary = shift_summary(db, shift)
    shift.closed_by_user_id = actor_user_id
    shift.closed_at = datetime.utcnow()
    shift.closing_cash_amount = closing_cash_amount
    shift.expected_cash_amount = summary["expected_cash_amount"]
    shift.cash_difference = money(closing_cash_amount - summary["expected_cash_amount"])
    shift.note = (note or "").strip() or None
    summary["closing_cash_amount"] = shift.closing_cash_amount
    summary["cash_difference"] = shift.cash_difference
    _audit(db, actor_user_id, "SHIFT_CLOSE", "shift", shift.id, new_value={"expected_cash_amount": str(shift.expected_cash_amount), "closing_cash_amount": str(shift.closing_cash_amount), "cash_difference": str(shift.cash_difference)}, reason=shift.note)
    return shift, summary


def change_guest_count(db: Session, actor_user_id: int, service_id: int, guest_count: int, reason: str) -> ServiceSession:
    require_permission(db, actor_user_id, "service.change_guest_count")
    if not 1 <= guest_count <= 50 or not reason.strip():
        raise PosError("INVALID_GUEST_COUNT", "1–50 kişi ve değişiklik nedeni zorunludur.", 422)
    service = db.scalar(select(ServiceSession).where(ServiceSession.id == service_id).with_for_update())
    if service is None or service.operational_status == ServiceStatus.CLOSED:
        raise PosError("SERVICE_NOT_ACTIVE", "Aktif servis bulunamadı.", 404)
    old_count = service.guest_count
    service.guest_count = guest_count
    service.version += 1
    _audit(db, actor_user_id, "GUEST_COUNT_CHANGE", "service_session", service.id, old_value={"guest_count": old_count}, new_value={"guest_count": guest_count}, reason=reason.strip())
    _event(db, "service.updated", "service_session", service.id, {"table_id": service.table_id})
    return service


def move_table(db: Session, actor_user_id: int, service_id: int, target_table_id: int, reason: str) -> ServiceSession:
    require_permission(db, actor_user_id, "service.move_table")
    if not reason.strip():
        raise PosError("REASON_REQUIRED", "Masa taşıma nedeni zorunludur.", 422)
    service = db.scalar(select(ServiceSession).where(ServiceSession.id == service_id).with_for_update())
    target = db.scalar(select(RestaurantTable).where(RestaurantTable.id == target_table_id).with_for_update())
    if service is None or service.operational_status == ServiceStatus.CLOSED or target is None or not target.is_active:
        raise PosError("MOVE_NOT_AVAILABLE", "Servis veya hedef masa taşıma için uygun değil.", 409)
    occupied = db.scalar(select(ServiceSession).where(ServiceSession.table_id == target_table_id, ServiceSession.operational_status.in_(ACTIVE_SERVICE_STATUSES)))
    if occupied is not None:
        raise PosError("TABLE_ALREADY_OPEN", "Hedef masada aktif servis bulunuyor.", 409)
    old_table_id = service.table_id
    service.table_id = target_table_id
    service.version += 1
    db.add(TableTransfer(service_session_id=service.id, from_table_id=old_table_id, to_table_id=target_table_id, reason=reason.strip(), actor_user_id=actor_user_id))
    _audit(db, actor_user_id, "TABLE_MOVE", "service_session", service.id, old_value={"table_id": old_table_id}, new_value={"table_id": target_table_id}, reason=reason.strip())
    _event(db, "table.updated", "service_session", service.id, {"from_table_id": old_table_id, "to_table_id": target_table_id})
    return service


def transfer_waiter(db: Session, actor_user_id: int, service_id: int, target_waiter_id: int, reason: str) -> ServiceSession:
    require_permission(db, actor_user_id, "service.transfer_waiter")
    if not reason.strip():
        raise PosError("REASON_REQUIRED", "Garson devir nedeni zorunludur.", 422)
    service = db.scalar(select(ServiceSession).where(ServiceSession.id == service_id).with_for_update())
    waiter = db.get(User, target_waiter_id)
    if service is None or service.operational_status == ServiceStatus.CLOSED or waiter is None or not waiter.is_active:
        raise PosError("TRANSFER_NOT_AVAILABLE", "Servis veya hedef garson devir için uygun değil.", 409)
    old_waiter_id = service.primary_waiter_id
    service.primary_waiter_id = target_waiter_id
    service.version += 1
    db.add(ServiceWaiterTransfer(service_session_id=service.id, from_waiter_id=old_waiter_id, to_waiter_id=target_waiter_id, reason=reason.strip(), requested_by_user_id=actor_user_id))
    _audit(db, actor_user_id, "WAITER_TRANSFER", "service_session", service.id, old_value={"waiter_id": old_waiter_id}, new_value={"waiter_id": target_waiter_id}, reason=reason.strip())
    _event(db, "service.updated", "service_session", service.id, {"table_id": service.table_id})
    return service


def merge_checks(db: Session, actor_user_id: int, target_check_id: int, source_check_id: int, reason: str) -> Check:
    require_permission(db, actor_user_id, "service.merge")
    if target_check_id == source_check_id or not reason.strip():
        raise PosError("INVALID_MERGE", "Farklı iki adisyon ve birleştirme nedeni zorunludur.", 422)
    locked = db.scalars(
        select(Check).where(Check.id.in_([target_check_id, source_check_id])).order_by(Check.id).with_for_update()
    ).all()
    by_id = {row.id: row for row in locked}
    target, source = by_id.get(target_check_id), by_id.get(source_check_id)
    if target is None or source is None or target.status == CheckStatus.CLOSED or source.status == CheckStatus.CLOSED:
        raise PosError("MERGE_NOT_AVAILABLE", "Birleştirilecek açık adisyonlar bulunamadı.", 409)
    recalculate_check(db, target); recalculate_check(db, source)
    if target.paid_total > 0 or source.paid_total > 0:
        raise PosError("MERGE_HAS_PAYMENTS", "Ödeme alınmış adisyonlar birleştirilemez; önce ödemeleri reverse edin.", 409)
    source_service = _service_for_check(db, source, lock=True)
    target_service = _service_for_check(db, target, lock=True)
    for row in db.scalars(select(CheckItem).where(CheckItem.check_id == source.id)).all():
        row.check_id = target.id
    for row in db.scalars(select(Discount).where(Discount.check_id == source.id)).all():
        row.check_id = target.id
    db.add(CheckMerge(target_check_id=target.id, source_check_id=source.id, reason=reason.strip(), created_by_user_id=actor_user_id))
    now = datetime.utcnow()
    source.status = CheckStatus.CLOSED
    source.closed_at = now
    source.closed_by_user_id = actor_user_id
    source.subtotal = source.discount_total = source.comp_total = source.final_total = source.paid_total = source.balance_due = Decimal("0.00")
    source_service.operational_status = ServiceStatus.CLOSED
    source_service.closed_at = now
    source_service.closed_by_user_id = actor_user_id
    recalculate_check(db, target)
    _audit(db, actor_user_id, "TABLE_MERGE", "check", target.id, new_value={"source_check_id": source.id, "target_check_id": target.id}, reason=reason.strip())
    _event(db, "check.updated", "check", target.id, {"table_id": target_service.table_id})
    _event(db, "service.closed", "service_session", source_service.id, {"table_id": source_service.table_id, "merged_into": target.id})
    return target


def split_check_to_table(
    db: Session,
    actor_user_id: int,
    source_check_id: int,
    target_table_id: int,
    guest_count: int,
    item_quantities: dict[int, Decimal],
    reason: str,
) -> Check:
    require_permission(db, actor_user_id, "service.split")
    if not reason.strip() or not 1 <= guest_count <= 50 or not item_quantities:
        raise PosError("INVALID_SPLIT", "Hedef masa, kişi sayısı, kalemler ve bölme nedeni zorunludur.", 422)
    source = _locked_check(db, source_check_id)
    if source.status == CheckStatus.CLOSED:
        raise PosError("CHECK_CLOSED", "Kapalı adisyon bölünemez.", 409)
    recalculate_check(db, source)
    if source.paid_total > 0:
        raise PosError("SPLIT_HAS_PAYMENTS", "Ödeme alınmış adisyon bölünemez; önce ödemeleri reverse edin.", 409)
    source_service = _service_for_check(db, source, lock=True)
    target_table = db.scalar(select(RestaurantTable).where(RestaurantTable.id == target_table_id).with_for_update())
    if target_table is None or not target_table.is_active:
        raise PosError("TABLE_NOT_FOUND", "Hedef masa bulunamadı.", 404)
    occupied = db.scalar(select(ServiceSession).where(ServiceSession.table_id == target_table_id, ServiceSession.operational_status.in_(ACTIVE_SERVICE_STATUSES)))
    if occupied is not None:
        raise PosError("TABLE_ALREADY_OPEN", "Hedef masada aktif servis bulunuyor.", 409)
    target_service = ServiceSession(
        table_id=target_table.id,
        primary_waiter_id=source_service.primary_waiter_id,
        guest_count=guest_count,
        operational_status=ServiceStatus.OPEN,
        opened_by_user_id=actor_user_id,
    )
    db.add(target_service); db.flush()
    target = Check(check_number=f"BS-{datetime.now():%y%m%d}-{target_service.id:06d}", service_session_id=target_service.id, status=CheckStatus.OPEN)
    db.add(target); db.flush()
    split = CheckSplit(source_check_id=source.id, target_check_id=target.id, reason=reason.strip(), created_by_user_id=actor_user_id)
    db.add(split); db.flush()

    source_items = {row.id: row for row in db.scalars(select(CheckItem).where(CheckItem.check_id == source.id, CheckItem.is_cancelled.is_(False))).all()}
    for item_id, requested_quantity in item_quantities.items():
        row = source_items.get(int(item_id))
        quantity = Decimal(requested_quantity)
        if row is None or quantity <= 0 or quantity > Decimal(row.quantity):
            raise PosError("INVALID_SPLIT_ITEM", "Bölünecek ürün adedi geçersiz.", 422)
        if quantity == Decimal(row.quantity):
            row.check_id = target.id
            target_item = row
        else:
            row.quantity = Decimal(row.quantity) - quantity
            row.line_total = money(Decimal(row.unit_price) * Decimal(row.quantity))
            row.version += 1
            target_item = CheckItem(
                check_id=target.id, product_id=row.product_id, product_name_snapshot=row.product_name_snapshot,
                unit_price=row.unit_price, quantity=quantity, line_total=money(Decimal(row.unit_price) * quantity),
                note=row.note, created_by_user_id=actor_user_id, is_comp=row.is_comp, comp_reason=row.comp_reason,
                comp_by_user_id=row.comp_by_user_id, comp_at=row.comp_at, price_override=row.price_override,
                original_unit_price=row.original_unit_price, price_override_reason=row.price_override_reason,
                price_overridden_by_user_id=row.price_overridden_by_user_id,
            )
            db.add(target_item); db.flush()
        db.add(CheckSplitMember(check_split_id=split.id, source_item_id=row.id, target_item_id=target_item.id, quantity=quantity))
    recalculate_check(db, source); recalculate_check(db, target)
    _audit(db, actor_user_id, "TABLE_SPLIT", "check", source.id, new_value={"target_check_id": target.id, "target_table_id": target_table.id}, reason=reason.strip())
    _event(db, "check.updated", "check", source.id, {"table_id": source_service.table_id})
    _event(db, "service.opened", "service_session", target_service.id, {"table_id": target_table.id, "check_id": target.id})
    return target


def create_section(db: Session, actor_user_id: int, name: str) -> TableSection:
    require_permission(db, actor_user_id, "tables.manage")
    if not name.strip():
        raise PosError("NAME_REQUIRED", "Salon adı zorunludur.", 422)
    if db.scalar(select(TableSection.id).where(func.lower(TableSection.name) == name.strip().lower())) is not None:
        raise PosError("SECTION_EXISTS", "Bu salon adı zaten kullanılıyor.", 409)
    row = TableSection(name=name.strip())
    db.add(row)
    db.flush()
    _audit(db, actor_user_id, "SECTION_CREATE", "table_section", row.id, new_value={"name": row.name})
    return row


def create_table(db: Session, actor_user_id: int, section_id: int, code: str, display_name: str, capacity: int) -> RestaurantTable:
    require_permission(db, actor_user_id, "tables.manage")
    if not code.strip() or not display_name.strip() or not 1 <= capacity <= 100:
        raise PosError("INVALID_TABLE", "Masa kodu, adı ve 1–100 kapasite zorunludur.", 422)
    if db.get(TableSection, section_id) is None:
        raise PosError("SECTION_NOT_FOUND", "Salon bulunamadı.", 404)
    if db.scalar(select(RestaurantTable.id).where(RestaurantTable.section_id == section_id, func.lower(RestaurantTable.code) == code.strip().lower())) is not None:
        raise PosError("TABLE_CODE_EXISTS", "Bu salonda aynı masa kodu zaten kullanılıyor.", 409)
    row = RestaurantTable(section_id=section_id, code=code.strip(), display_name=display_name.strip(), capacity=capacity)
    db.add(row)
    db.flush()
    _audit(db, actor_user_id, "TABLE_CREATE", "restaurant_table", row.id, new_value={"code": row.code, "name": row.display_name})
    return row


def create_category(db: Session, actor_user_id: int, name: str) -> Category:
    require_permission(db, actor_user_id, "products.manage")
    if not name.strip():
        raise PosError("NAME_REQUIRED", "Kategori adı zorunludur.", 422)
    if db.scalar(select(Category.id).where(func.lower(Category.name) == name.strip().lower())) is not None:
        raise PosError("CATEGORY_EXISTS", "Bu kategori adı zaten kullanılıyor.", 409)
    row = Category(name=name.strip())
    db.add(row)
    db.flush()
    _audit(db, actor_user_id, "CATEGORY_CREATE", "category", row.id, new_value={"name": row.name})
    return row


def create_product(db: Session, actor_user_id: int, category_id: int, name: str, price: Decimal, is_favorite: bool = False) -> Product:
    require_permission(db, actor_user_id, "products.manage")
    price = money(price)
    if not name.strip() or price < 0 or db.get(Category, category_id) is None:
        raise PosError("INVALID_PRODUCT", "Geçerli kategori, ürün adı ve fiyat zorunludur.", 422)
    row = Product(category_id=category_id, name=name.strip(), price=price, is_favorite=is_favorite)
    db.add(row)
    db.flush()
    _audit(db, actor_user_id, "PRODUCT_CREATE", "product", row.id, new_value={"name": row.name, "price": str(row.price), "is_favorite": row.is_favorite})
    return row
