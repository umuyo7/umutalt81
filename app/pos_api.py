from __future__ import annotations

import asyncio
import csv
import hmac
import json
from datetime import date, datetime
from decimal import Decimal
from io import StringIO

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .auth_session import authenticated_user
from .db import SessionLocal, get_db
from .models import BusinessType, User
from .permissions import permission_decision, require_permission
from .pos_models import (
    AuditLog,
    Category,
    Check,
    CheckItem,
    Discount,
    OutboxEvent,
    Payment,
    PaymentStatus,
    Product,
    RestaurantTable,
    Role,
    Permission,
    PermissionEffect,
    RolePermission,
    ServiceSession,
    ServiceStatus,
    Shift,
    TableSection,
    UserRole,
)
from .pos_schemas import (
    CategoryCreateRequest,
    DailyMenuUpdateRequest,
    DiscountRequest,
    GuestCountRequest,
    ItemAddRequest,
    MergeChecksRequest,
    NamedActiveUpdateRequest,
    MoveTableRequest,
    PaymentRequest,
    PaymentMethodChangeRequest,
    PriceOverrideRequest,
    ProductCreateRequest,
    ProductUpdateRequest,
    QuantityRequest,
    ReasonRequest,
    SectionCreateRequest,
    ServiceOpenRequest,
    ShiftCloseRequest,
    ShiftOpenRequest,
    SplitCheckRequest,
    TableCreateRequest,
    TableUpdateRequest,
    TransferWaiterRequest,
    UserCreateRequest,
    UserUpdateRequest,
    RolePermissionsUpdateRequest,
)
from .pos_services import (
    ACTIVE_SERVICE_STATUSES,
    PosError,
    active_check_request,
    add_item,
    apply_discount,
    cancel_check_request,
    cancel_item,
    change_guest_count,
    change_payment_method,
    close_check,
    comp_item,
    create_category,
    create_payment,
    create_product,
    create_section,
    create_table,
    force_close_check,
    move_table,
    merge_checks,
    open_service,
    open_shift,
    set_daily_menu,
    recalculate_check,
    remove_discount,
    reopen_check,
    request_check,
    send_to_kitchen,
    shift_summary,
    close_shift,
    reverse_payment,
    transfer_waiter,
    split_check_to_table,
    update_item_quantity,
    override_item_price,
)
from .security import hash_password
from .reporting import operation_report
from .request_context import bind_session, current_request_context


router = APIRouter(prefix="/api/v1", tags=["pos"])


def ok(data, status: int | None = None) -> dict:
    payload = {"success": True, "data": data}
    if status is not None:
        payload["status"] = status
    return payload


def decimal_strings(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: decimal_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decimal_strings(item) for item in value]
    return value


def actor(request: Request, db: Session = Depends(get_db)) -> User:
    user = authenticated_user(request, db)
    if user is None:
        raise PosError("AUTH_REQUIRED", "Oturum açmanız gerekiyor.", 401)
    if user.business_type != BusinessType.RESTAURANT:
        raise PosError("POS_ACCESS_DENIED", "Bu hesap POS alanına erişemez.", 403)
    bind_session(request.session.get("login_session_id"))
    return user


def csrf_guard(request: Request, x_csrf_token: str | None = Header(default=None)) -> None:
    expected = request.session.get("csrf_token", "")
    if not expected or not x_csrf_token or not hmac.compare_digest(expected, x_csrf_token):
        raise PosError("CSRF_INVALID", "Geçersiz veya süresi dolmuş işlem isteği.", 403)


def commit_command(db: Session, callback):
    try:
        result = callback()
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def add_audit(db: Session, actor_user_id: int, action: str, entity_type: str, entity_id: int | str, *, old_value=None, new_value=None, reason: str | None = None) -> None:
    context = current_request_context()
    db.add(AuditLog(
        actor_user_id=actor_user_id, action=action, entity_type=entity_type, entity_id=str(entity_id),
        old_value=old_value, new_value=new_value, reason=reason,
        ip_address=context.get("ip_address"), user_agent=context.get("user_agent"),
        session_id=context.get("session_id"), request_id=context.get("request_id"),
    ))


def check_payload(db: Session, check: Check) -> dict:
    service = db.get(ServiceSession, check.service_session_id)
    table = db.get(RestaurantTable, service.table_id) if service else None
    waiter = db.get(User, service.primary_waiter_id) if service else None
    items = db.scalars(select(CheckItem).where(CheckItem.check_id == check.id).order_by(CheckItem.created_at, CheckItem.id)).all()
    discounts = db.scalars(select(Discount).where(Discount.check_id == check.id).order_by(Discount.id)).all()
    payments = db.scalars(select(Payment).where(Payment.check_id == check.id).order_by(Payment.created_at, Payment.id)).all()
    return {
        "id": check.id,
        "check_number": check.check_number,
        "status": check.status.value,
        "version": check.version,
        "table": {"id": table.id, "name": table.display_name} if table else None,
        "service": {
            "id": service.id,
            "guest_count": service.guest_count,
            "status": service.operational_status.value,
            "check_requested": active_check_request(service),
            "opened_at": service.opened_at.isoformat(),
        } if service else None,
        "waiter": {"id": waiter.id, "name": waiter.name} if waiter else None,
        "totals": {
            "subtotal": str(check.subtotal),
            "discount": str(check.discount_total),
            "comp": str(check.comp_total),
            "final": str(check.final_total),
            "paid": str(check.paid_total),
            "balance": str(check.balance_due),
        },
        "items": [
            {
                "id": row.id,
                "name": row.product_name_snapshot,
                "unit_price": str(row.unit_price),
                "quantity": str(row.quantity),
                "line_total": str(row.line_total),
                "note": row.note,
                "cancelled": row.is_cancelled,
                "cancel_reason": row.cancel_reason,
                "comp": row.is_comp,
                "comp_reason": row.comp_reason,
            }
            for row in items
        ],
        "discounts": [
            {"id": row.id, "type": row.discount_type.value, "value": str(row.value), "amount": str(row.calculated_amount), "status": row.status.value}
            for row in discounts
        ],
        "payments": [
            {"id": row.id, "method": row.payment_method.value, "amount": str(row.amount), "status": row.status.value, "created_at": row.created_at.isoformat()}
            for row in payments
        ],
    }


@router.get("/me")
def me(user: User = Depends(actor), db: Session = Depends(get_db)):
    codes = [
        "service.open", "order.add_item", "payment.create", "payment.create_without_check_request",
        "payment.close_check", "check.reopen", "users.manage", "products.manage", "tables.manage",
    ]
    return ok({"id": user.id, "name": user.name, "username": user.username, "permissions": {code: permission_decision(db, user.id, code).allowed for code in codes}})


@router.get("/events")
async def events(request: Request, user: User = Depends(actor)):
    async def stream():
        cursor = datetime.utcnow()
        yield ": connected\n\n"
        while not await request.is_disconnected():
            with SessionLocal() as event_db:
                rows = event_db.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.occurred_at > cursor)
                    .order_by(OutboxEvent.occurred_at, OutboxEvent.id)
                    .limit(100)
                ).all()
                for row in rows:
                    cursor = max(cursor, row.occurred_at)
                    payload = {"type": row.event_type, "aggregate_type": row.aggregate_type, "aggregate_id": row.aggregate_id, "payload": row.payload}
                    yield f"id: {row.id}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/tables")
def list_tables(user: User = Depends(actor), db: Session = Depends(get_db)):
    rows = db.execute(
        select(RestaurantTable, TableSection, ServiceSession, Check, User)
        .join(TableSection, TableSection.id == RestaurantTable.section_id)
        .outerjoin(
            ServiceSession,
            and_(ServiceSession.table_id == RestaurantTable.id, ServiceSession.operational_status.in_(ACTIVE_SERVICE_STATUSES)),
        )
        .outerjoin(Check, Check.service_session_id == ServiceSession.id)
        .outerjoin(User, User.id == ServiceSession.primary_waiter_id)
        .where(RestaurantTable.is_active.is_(True), TableSection.is_active.is_(True))
        .order_by(TableSection.sort_order, RestaurantTable.sort_order, RestaurantTable.id)
    ).all()
    return ok([
        {
            "id": table.id,
            "name": table.display_name,
            "code": table.code,
            "section": section.name,
            "capacity": table.capacity,
            "status": service.operational_status.value if service else "EMPTY",
            "guest_count": service.guest_count if service else None,
            "waiter": waiter.name if waiter else None,
            "check_id": check.id if check else None,
            "check_number": check.check_number if check else None,
            "total": str(check.final_total) if check else "0.00",
            "opened_at": service.opened_at.isoformat() if service else None,
        }
        for table, section, service, check, waiter in rows
    ])


@router.post("/services", dependencies=[Depends(csrf_guard)])
def service_open(payload: ServiceOpenRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    service, check = commit_command(db, lambda: open_service(db, user.id, payload.table_id, payload.guest_count))
    return ok({"service_id": service.id, "check_id": check.id, "check_number": check.check_number})


@router.post("/services/{service_id}/move-table", dependencies=[Depends(csrf_guard)])
def service_move(service_id: int, payload: MoveTableRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    service = commit_command(db, lambda: move_table(db, user.id, service_id, payload.target_table_id, payload.reason))
    return ok({"service_id": service.id, "table_id": service.table_id})


@router.post("/services/{service_id}/change-guest-count", dependencies=[Depends(csrf_guard)])
def service_guest_count(service_id: int, payload: GuestCountRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    service = commit_command(db, lambda: change_guest_count(db, user.id, service_id, payload.guest_count, payload.reason))
    return ok({"service_id": service.id, "guest_count": service.guest_count})


@router.post("/services/{service_id}/transfer-waiter", dependencies=[Depends(csrf_guard)])
def service_transfer(service_id: int, payload: TransferWaiterRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    service = commit_command(db, lambda: transfer_waiter(db, user.id, service_id, payload.target_waiter_id, payload.reason))
    return ok({"service_id": service.id, "waiter_id": service.primary_waiter_id})


@router.get("/checks")
def list_checks(status: str = "open", user: User = Depends(actor), db: Session = Depends(get_db)):
    statement = select(Check).order_by(Check.opened_at.desc())
    if status == "closed":
        statement = statement.where(Check.status == "CLOSED")
    else:
        statement = statement.where(Check.status != "CLOSED")
    rows = db.scalars(statement.limit(200)).all()
    return ok([check_payload(db, row) for row in rows])


@router.get("/checks/{check_id}")
def get_check(check_id: int, user: User = Depends(actor), db: Session = Depends(get_db)):
    check = db.get(Check, check_id)
    if check is None:
        raise PosError("CHECK_NOT_FOUND", "Adisyon bulunamadı.", 404)
    return ok(check_payload(db, check))


@router.post("/checks/{check_id}/items", dependencies=[Depends(csrf_guard)])
def item_add(check_id: int, payload: ItemAddRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    row = commit_command(db, lambda: add_item(db, user.id, check_id, payload.product_id, payload.quantity, payload.note))
    return ok({"item_id": row.id, "message": f"{row.product_name_snapshot} eklendi"})


@router.post("/tables/{table_id}/kitchen-send", dependencies=[Depends(csrf_guard)])
def kitchen_send(table_id: int, user: User = Depends(actor), db: Session = Depends(get_db)):
    check, _, items, sent_at = commit_command(db, lambda: send_to_kitchen(db, user.id, table_id))
    return ok({"check_id": check.id, "item_ids": [item.id for item in items], "sent_at": sent_at.isoformat()})


@router.get("/shifts/current")
def current_shift(user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "shift.open")
    shift = db.scalar(select(Shift).where(Shift.closed_at.is_(None)).order_by(Shift.opened_at.desc()))
    if shift is None:
        return ok(None)
    return ok(decimal_strings({"id": shift.id, "opened_at": shift.opened_at.isoformat(), "opening_cash_amount": shift.opening_cash_amount, **shift_summary(db, shift)}))


@router.post("/shifts/open", dependencies=[Depends(csrf_guard)])
def shift_open(payload: ShiftOpenRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    shift = commit_command(db, lambda: open_shift(db, user.id, payload.opening_cash_amount))
    return ok({"id": shift.id, "opened_at": shift.opened_at.isoformat()})


@router.post("/shifts/close", dependencies=[Depends(csrf_guard)])
def shift_close(payload: ShiftCloseRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    shift, summary = commit_command(db, lambda: close_shift(db, user.id, payload.closing_cash_amount, payload.note))
    return ok(decimal_strings({"id": shift.id, "closed_at": shift.closed_at.isoformat(), **summary}))


@router.patch("/checks/{check_id}/items/{item_id}", dependencies=[Depends(csrf_guard)])
def item_quantity(check_id: int, item_id: int, payload: QuantityRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    row = commit_command(db, lambda: update_item_quantity(db, user.id, item_id, payload.quantity))
    return ok({"item_id": row.id, "quantity": str(row.quantity)})


@router.post("/checks/{check_id}/items/{item_id}/cancel", dependencies=[Depends(csrf_guard)])
def item_cancel(check_id: int, item_id: int, payload: ReasonRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    row = commit_command(db, lambda: cancel_item(db, user.id, item_id, payload.reason))
    return ok({"item_id": row.id, "cancelled": True})


@router.post("/checks/{check_id}/items/{item_id}/comp", dependencies=[Depends(csrf_guard)])
def item_comp(check_id: int, item_id: int, payload: ReasonRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    row = commit_command(db, lambda: comp_item(db, user.id, item_id, payload.reason))
    return ok({"item_id": row.id, "comp": True})


@router.post("/checks/{check_id}/items/{item_id}/override-price", dependencies=[Depends(csrf_guard)])
def item_price_override(check_id: int, item_id: int, payload: PriceOverrideRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    row = commit_command(db, lambda: override_item_price(db, user.id, item_id, payload.unit_price, payload.reason))
    return ok({"item_id": row.id, "unit_price": str(row.unit_price)})


@router.post("/checks/{check_id}/discounts", dependencies=[Depends(csrf_guard)])
def discount_add(check_id: int, payload: DiscountRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    row = commit_command(db, lambda: apply_discount(db, user.id, check_id, payload.discount_type, payload.value, payload.reason))
    return ok({"discount_id": row.id, "amount": str(row.calculated_amount)})


@router.post("/checks/{check_id}/discounts/{discount_id}/remove", dependencies=[Depends(csrf_guard)])
def discount_remove(check_id: int, discount_id: int, payload: ReasonRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    row = commit_command(db, lambda: remove_discount(db, user.id, discount_id, payload.reason))
    return ok({"discount_id": row.id, "status": row.status.value})


@router.post("/checks/{check_id}/request-check", dependencies=[Depends(csrf_guard)])
def check_request(check_id: int, user: User = Depends(actor), db: Session = Depends(get_db)):
    service = commit_command(db, lambda: request_check(db, user.id, check_id))
    return ok({"check_id": check_id, "status": service.operational_status.value})


@router.post("/checks/{check_id}/cancel-check-request", dependencies=[Depends(csrf_guard)])
def check_request_cancel(check_id: int, user: User = Depends(actor), db: Session = Depends(get_db)):
    service = commit_command(db, lambda: cancel_check_request(db, user.id, check_id))
    return ok({"check_id": check_id, "status": service.operational_status.value})


@router.post("/checks/{check_id}/close", dependencies=[Depends(csrf_guard)])
def check_close(check_id: int, user: User = Depends(actor), db: Session = Depends(get_db)):
    check = commit_command(db, lambda: close_check(db, user.id, check_id))
    return ok({"check_id": check.id, "status": check.status.value})


@router.post("/checks/{check_id}/force-close", dependencies=[Depends(csrf_guard)])
def check_force_close(check_id: int, payload: ReasonRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    check = commit_command(db, lambda: force_close_check(db, user.id, check_id, payload.reason))
    return ok({"check_id": check.id, "status": check.status.value})


@router.post("/checks/{check_id}/reopen", dependencies=[Depends(csrf_guard)])
def check_reopen(check_id: int, payload: ReasonRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    check = commit_command(db, lambda: reopen_check(db, user.id, check_id, payload.reason))
    return ok({"check_id": check.id, "status": check.status.value})


@router.post("/checks/{check_id}/merge", dependencies=[Depends(csrf_guard)])
def check_merge(check_id: int, payload: MergeChecksRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    check = commit_command(db, lambda: merge_checks(db, user.id, check_id, payload.source_check_id, payload.reason))
    return ok({"check_id": check.id, "merged_source_check_id": payload.source_check_id, "total": str(check.final_total)})


@router.post("/checks/{check_id}/split", dependencies=[Depends(csrf_guard)])
def check_split(check_id: int, payload: SplitCheckRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    target = commit_command(db, lambda: split_check_to_table(db, user.id, check_id, payload.target_table_id, payload.guest_count, payload.item_quantities, payload.reason))
    return ok({"source_check_id": check_id, "target_check_id": target.id, "target_total": str(target.final_total)})


@router.post("/payments", dependencies=[Depends(csrf_guard)])
def payment_create(
    payload: PaymentRequest,
    user: User = Depends(actor),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    payment, replayed, notice = commit_command(
        db,
        lambda: create_payment(db, user.id, payload.check_id, payload.payment_method, payload.amount, idempotency_key or "", payload.external_reference, payload.notes),
    )
    return ok({"payment_id": payment.id, "check_id": payment.check_id, "amount": str(payment.amount), "replayed": replayed, "notice": notice})


@router.post("/payments/{payment_id}/reverse", dependencies=[Depends(csrf_guard)])
def payment_reverse(payment_id: int, payload: ReasonRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    payment = commit_command(db, lambda: reverse_payment(db, user.id, payment_id, payload.reason))
    return ok({"payment_id": payment.id, "status": payment.status.value})


@router.post("/payments/{payment_id}/change-method", dependencies=[Depends(csrf_guard)])
def payment_method_change(payment_id: int, payload: PaymentMethodChangeRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    replacement = commit_command(db, lambda: change_payment_method(db, user.id, payment_id, payload.payment_method, payload.reason))
    return ok({"payment_id": replacement.id, "method": replacement.payment_method.value, "replaces": replacement.reverses_payment_id})


@router.get("/categories")
def categories(user: User = Depends(actor), db: Session = Depends(get_db)):
    rows = db.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name)).all()
    return ok([{"id": row.id, "name": row.name} for row in rows])


@router.get("/products")
def products(category_id: int | None = None, user: User = Depends(actor), db: Session = Depends(get_db)):
    statement = select(Product).join(Category, Category.id == Product.category_id).where(Product.is_active.is_(True), Category.is_active.is_(True))
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    rows = db.scalars(statement.order_by(Product.is_favorite.desc(), Product.sort_order, Product.name)).all()
    return ok([{"id": row.id, "category_id": row.category_id, "name": row.name, "price": str(row.price), "is_favorite": row.is_favorite} for row in rows])


@router.post("/menu/daily-picks", dependencies=[Depends(csrf_guard)])
def daily_menu_update(payload: DailyMenuUpdateRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    picked = commit_command(db, lambda: set_daily_menu(db, user.id, payload.product_ids))
    return ok({"product_ids": sorted(row.id for row in picked)})


@router.post("/admin/sections", dependencies=[Depends(csrf_guard)])
def section_create(payload: SectionCreateRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    row = commit_command(db, lambda: create_section(db, user.id, payload.name))
    return ok({"id": row.id, "name": row.name})


@router.post("/admin/tables", dependencies=[Depends(csrf_guard)])
def table_create(payload: TableCreateRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    row = commit_command(db, lambda: create_table(db, user.id, payload.section_id, payload.code, payload.display_name, payload.capacity))
    return ok({"id": row.id, "name": row.display_name})


@router.post("/admin/categories", dependencies=[Depends(csrf_guard)])
def category_create(payload: CategoryCreateRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    row = commit_command(db, lambda: create_category(db, user.id, payload.name))
    return ok({"id": row.id, "name": row.name})


@router.post("/admin/products", dependencies=[Depends(csrf_guard)])
def product_create(payload: ProductCreateRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    row = commit_command(db, lambda: create_product(db, user.id, payload.category_id, payload.name, payload.price, payload.is_favorite))
    return ok({"id": row.id, "name": row.name, "price": str(row.price), "is_favorite": row.is_favorite})


@router.post("/admin/users", dependencies=[Depends(csrf_guard)])
def user_create(payload: UserCreateRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "users.manage")
    if db.scalar(select(User).where(User.username == payload.username.lower())) is not None:
        raise PosError("USERNAME_EXISTS", "Bu kullanıcı adı zaten kullanılıyor.", 409)
    role = db.scalar(select(Role).where(Role.code == payload.role_code, Role.is_active.is_(True)))
    if role is None:
        raise PosError("ROLE_NOT_FOUND", "Rol bulunamadı.", 404)
    created = User(name=payload.name.strip(), username=payload.username.lower(), password_hash=hash_password(payload.password), business_type=BusinessType.RESTAURANT)
    db.add(created)
    db.flush()
    db.add(UserRole(user_id=created.id, role_id=role.id, assigned_by_user_id=user.id))
    add_audit(db, user.id, "USER_CREATE", "user", created.id, new_value={"username": created.username, "role": role.code})
    db.commit()
    return ok({"id": created.id, "username": created.username, "role": role.code})


@router.get("/admin/users")
def users(user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "users.manage")
    rows = db.execute(select(User, Role).outerjoin(UserRole, UserRole.user_id == User.id).outerjoin(Role, Role.id == UserRole.role_id).where(User.business_type == BusinessType.RESTAURANT).order_by(User.name)).all()
    return ok([{"id": row.id, "name": row.name, "username": row.username, "active": row.is_active, "role": role.code if role else None} for row, role in rows])


@router.patch("/admin/sections/{section_id}", dependencies=[Depends(csrf_guard)])
def section_update(section_id: int, payload: NamedActiveUpdateRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "tables.manage")
    section = db.get(TableSection, section_id)
    if section is None:
        raise PosError("SECTION_NOT_FOUND", "Salon bulunamadı.", 404)
    duplicate = db.scalar(select(TableSection.id).where(func.lower(TableSection.name) == payload.name.strip().lower(), TableSection.id != section.id))
    if duplicate is not None:
        raise PosError("SECTION_EXISTS", "Bu salon adı zaten kullanılıyor.", 409)
    if not payload.is_active:
        active_service = db.scalar(select(ServiceSession.id).join(RestaurantTable, RestaurantTable.id == ServiceSession.table_id).where(RestaurantTable.section_id == section.id, ServiceSession.operational_status.in_(ACTIVE_SERVICE_STATUSES)))
        if active_service is not None:
            raise PosError("ACTIVE_SECTION_DEACTIVATE_DENIED", "Aktif servisi olan salon pasifleştirilemez.", 409)
    old = {"name": section.name, "active": section.is_active}
    section.name = payload.name.strip(); section.is_active = payload.is_active
    add_audit(db, user.id, "SECTION_UPDATE", "table_section", section.id, old_value=old, new_value={"name": section.name, "active": section.is_active}, reason=payload.reason)
    db.commit()
    return ok({"id": section.id, "name": section.name, "active": section.is_active})


@router.patch("/admin/categories/{category_id}", dependencies=[Depends(csrf_guard)])
def category_update(category_id: int, payload: NamedActiveUpdateRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "products.manage")
    category = db.get(Category, category_id)
    if category is None:
        raise PosError("CATEGORY_NOT_FOUND", "Kategori bulunamadı.", 404)
    duplicate = db.scalar(select(Category.id).where(func.lower(Category.name) == payload.name.strip().lower(), Category.id != category.id))
    if duplicate is not None:
        raise PosError("CATEGORY_EXISTS", "Bu kategori adı zaten kullanılıyor.", 409)
    old = {"name": category.name, "active": category.is_active}
    category.name = payload.name.strip(); category.is_active = payload.is_active
    add_audit(db, user.id, "CATEGORY_UPDATE", "category", category.id, old_value=old, new_value={"name": category.name, "active": category.is_active}, reason=payload.reason)
    db.commit()
    return ok({"id": category.id, "name": category.name, "active": category.is_active})


@router.patch("/admin/users/{user_id}", dependencies=[Depends(csrf_guard)])
def user_update(user_id: int, payload: UserUpdateRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "users.manage")
    target = db.get(User, user_id)
    role = db.scalar(select(Role).where(Role.code == payload.role_code, Role.is_active.is_(True)))
    if target is None or target.business_type != BusinessType.RESTAURANT or role is None:
        raise PosError("USER_OR_ROLE_NOT_FOUND", "Kullanıcı veya rol bulunamadı.", 404)
    if target.id == user.id and not payload.is_active:
        raise PosError("SELF_DEACTIVATE_DENIED", "Kendi hesabınızı pasifleştiremezsiniz.", 409)
    old = {"name": target.name, "active": target.is_active, "roles": [code for code in db.scalars(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == target.id)).all()]}
    target.name = payload.name.strip()
    target.is_active = payload.is_active
    db.query(UserRole).filter(UserRole.user_id == target.id).delete(synchronize_session=False)
    db.add(UserRole(user_id=target.id, role_id=role.id, assigned_by_user_id=user.id))
    add_audit(db, user.id, "USER_UPDATE", "user", target.id, old_value=old, new_value={"name": target.name, "active": target.is_active, "role": role.code}, reason=payload.reason)
    db.commit()
    return ok({"id": target.id, "name": target.name, "active": target.is_active, "role": role.code})


@router.patch("/admin/products/{product_id}", dependencies=[Depends(csrf_guard)])
def product_update(product_id: int, payload: ProductUpdateRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "products.manage")
    product = db.get(Product, product_id)
    category = db.get(Category, payload.category_id)
    if product is None or category is None:
        raise PosError("PRODUCT_OR_CATEGORY_NOT_FOUND", "Ürün veya kategori bulunamadı.", 404)
    old = {"name": product.name, "category_id": product.category_id, "price": str(product.price), "active": product.is_active, "is_favorite": product.is_favorite}
    product.name = payload.name.strip(); product.category_id = category.id; product.price = payload.price; product.is_active = payload.is_active; product.is_favorite = payload.is_favorite; product.version += 1
    add_audit(db, user.id, "PRODUCT_UPDATE", "product", product.id, old_value=old, new_value={"name": product.name, "category_id": product.category_id, "price": str(product.price), "active": product.is_active, "is_favorite": product.is_favorite}, reason=payload.reason)
    db.commit()
    return ok({"id": product.id, "name": product.name, "price": str(product.price), "active": product.is_active, "is_favorite": product.is_favorite})


@router.patch("/admin/tables/{table_id}", dependencies=[Depends(csrf_guard)])
def table_update(table_id: int, payload: TableUpdateRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "tables.manage")
    table = db.get(RestaurantTable, table_id)
    if table is None:
        raise PosError("TABLE_NOT_FOUND", "Masa bulunamadı.", 404)
    if not payload.is_active and db.scalar(select(ServiceSession.id).where(ServiceSession.table_id == table.id, ServiceSession.operational_status.in_(ACTIVE_SERVICE_STATUSES))) is not None:
        raise PosError("ACTIVE_TABLE_DEACTIVATE_DENIED", "Aktif servisi olan masa pasifleştirilemez.", 409)
    old = {"name": table.display_name, "capacity": table.capacity, "active": table.is_active}
    table.display_name = payload.display_name.strip(); table.capacity = payload.capacity; table.is_active = payload.is_active; table.version += 1
    add_audit(db, user.id, "TABLE_UPDATE", "restaurant_table", table.id, old_value=old, new_value={"name": table.display_name, "capacity": table.capacity, "active": table.is_active}, reason=payload.reason)
    db.commit()
    return ok({"id": table.id, "name": table.display_name, "capacity": table.capacity, "active": table.is_active})


@router.get("/admin/roles")
def roles(user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "settings.manage")
    role_rows = db.scalars(select(Role).order_by(Role.id)).all()
    permissions = db.scalars(select(Permission).order_by(Permission.code)).all()
    grants = db.execute(select(RolePermission, Permission).join(Permission, Permission.id == RolePermission.permission_id)).all()
    by_role: dict[int, list[dict]] = {row.id: [] for row in role_rows}
    for grant, permission in grants:
        by_role.setdefault(grant.role_id, []).append({"code": permission.code, "effect": grant.effect.value, "limit": str(grant.limit_value_numeric) if grant.limit_value_numeric is not None else None})
    return ok({"roles": [{"id": row.id, "code": row.code, "name": row.name, "permissions": by_role.get(row.id, [])} for row in role_rows], "permissions": [{"code": row.code, "description": row.description, "value_type": row.value_type.value} for row in permissions]})


@router.put("/admin/roles/{role_id}/permissions", dependencies=[Depends(csrf_guard)])
def role_permissions_update(role_id: int, payload: RolePermissionsUpdateRequest, user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "settings.manage")
    role = db.get(Role, role_id)
    all_permissions = {row.code: row for row in db.scalars(select(Permission)).all()}
    requested = set(payload.permission_codes)
    unknown = requested - set(all_permissions)
    if role is None or unknown:
        raise PosError("ROLE_OR_PERMISSION_NOT_FOUND", "Rol veya permission kodu bulunamadı.", 404)
    existing = {row.permission_id: row for row in db.scalars(select(RolePermission).where(RolePermission.role_id == role.id)).all()}
    before = [code for code, permission in all_permissions.items() if permission.id in existing and existing[permission.id].effect == PermissionEffect.ALLOW]
    for code, permission in all_permissions.items():
        grant = existing.get(permission.id)
        if grant is None:
            grant = RolePermission(role_id=role.id, permission_id=permission.id)
            db.add(grant)
        grant.effect = PermissionEffect.ALLOW if code in requested else PermissionEffect.DENY
        grant.limit_value_numeric = payload.discount_max_percent if code == "discount.max_percent" and code in requested else None
    add_audit(db, user.id, "ROLE_PERMISSIONS_UPDATE", "role", role.id, old_value={"allowed": sorted(before)}, new_value={"allowed": sorted(requested), "discount_max_percent": str(payload.discount_max_percent)}, reason=payload.reason)
    db.commit()
    return ok({"role": role.code, "allowed": sorted(requested), "discount_max_percent": str(payload.discount_max_percent)})


def _daily_report_data(db: Session, report_date: date) -> dict:
    report_date = report_date or date.today()
    closed = db.scalars(select(Check).where(Check.status == "CLOSED", func.date(Check.closed_at) == report_date)).all()
    service_ids = [row.service_session_id for row in closed]
    guests = db.scalar(select(func.coalesce(func.sum(ServiceSession.guest_count), 0)).where(ServiceSession.id.in_(service_ids))) if service_ids else 0
    payment_rows = db.execute(
        select(Payment.payment_method, func.sum(Payment.amount))
        .join(Check, Check.id == Payment.check_id)
        .where(Payment.status == PaymentStatus.COMPLETED, Check.status == "CLOSED", func.date(Check.closed_at) == report_date)
        .group_by(Payment.payment_method)
    ).all()
    gross = sum((Decimal(row.subtotal) for row in closed), Decimal("0"))
    discount = sum((Decimal(row.discount_total) for row in closed), Decimal("0"))
    comp = sum((Decimal(row.comp_total) for row in closed), Decimal("0"))
    net = sum((Decimal(row.final_total) for row in closed), Decimal("0"))
    return {
        "date": report_date.isoformat(), "checks": len(closed), "guests": int(guests or 0),
        "gross": str(gross), "discount": str(discount), "comp": str(comp), "net": str(net),
        "per_guest": str((net / Decimal(guests)).quantize(Decimal('0.01')) if guests else Decimal('0.00')),
        "payments": {method.value: str(amount) for method, amount in payment_rows},
    }


@router.get("/reports/daily")
def daily_report(report_date: date | None = None, user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "reports.view")
    return ok(_daily_report_data(db, report_date or date.today()))


@router.get("/reports/daily.csv")
def daily_report_csv(report_date: date | None = None, user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "reports.export")
    data = _daily_report_data(db, report_date or date.today())
    output = StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Tarih", "Kapalı adisyon", "Misafir", "Brüt", "İndirim", "İkram", "Net", "Kişi başı"])
    writer.writerow([data["date"], data["checks"], data["guests"], data["gross"], data["discount"], data["comp"], data["net"], data["per_guest"]])
    writer.writerow([])
    writer.writerow(["Ödeme yöntemi", "Tutar"])
    for method, amount in sorted(data["payments"].items()):
        writer.writerow([method, amount])
    body = "\ufeff" + output.getvalue()
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bereket-gunluk-{data["date"]}.csv"'},
    )


@router.get("/reports/operations")
def operations_report(date_from: date, date_to: date, user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "reports.view")
    try:
        return ok(decimal_strings(operation_report(db, date_from, date_to)))
    except ValueError as exc:
        raise PosError("INVALID_REPORT_RANGE", str(exc), 422) from exc


@router.get("/reports/operations.csv")
def operations_report_csv(date_from: date, date_to: date, user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "reports.export")
    try:
        data = operation_report(db, date_from, date_to)
    except ValueError as exc:
        raise PosError("INVALID_REPORT_RANGE", str(exc), 422) from exc
    output = StringIO(); writer = csv.writer(output, delimiter=";")
    summary = data["summary"]
    writer.writerow(["Başlangıç", "Bitiş", "Brüt", "Net", "İndirim", "İkram", "İptal", "Misafir", "Kişi başı", "Adisyon", "Ortalama masa", "Ortalama servis dk"])
    writer.writerow([data["date_from"], data["date_to"], summary["gross"], summary["net"], summary["discount"], summary["comp"], summary["cancelled"], summary["guests"], summary["per_guest"], summary["checks"], summary["average_table"], summary["average_service_minutes"]])
    for title, rows, columns in (
        ("Ödeme yöntemleri", [{"name": key, "amount": value} for key, value in data["payments"].items()], [("Yöntem", "name"), ("Tutar", "amount")]),
        ("Garson performansı", data["waiters"], [("Garson", "name"), ("Servis", "services"), ("Misafir", "guests"), ("Net", "net"), ("Kişi başı", "per_guest"), ("Ortalama masa", "average_table"), ("İndirim", "discount"), ("İkram", "comp"), ("İptal", "cancelled")]),
        ("Ürün satışı", data["products"], [("Ürün", "name"), ("Adet", "quantity"), ("Brüt", "gross"), ("İkram", "comp"), ("Net", "net")]),
        ("Kategori satışı", data["categories"], [("Kategori", "name"), ("Adet", "quantity"), ("Brüt", "gross"), ("İkram", "comp"), ("Net", "net")]),
        ("Saatlik satış", data["hourly"], [("Saat", "hour"), ("Net", "net")]),
    ):
        writer.writerow([]); writer.writerow([title]); writer.writerow([label for label, _ in columns])
        for row in rows:
            writer.writerow([row[key] for _, key in columns])
    body = "\ufeff" + output.getvalue()
    return Response(body, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="bereket-rapor-{date_from}-{date_to}.csv"'})


@router.get("/audit")
def audit(limit: int = 100, user: User = Depends(actor), db: Session = Depends(get_db)):
    require_permission(db, user.id, "reports.view")
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 500))).all()
    return ok([{"id": row.id, "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "actor_user_id": row.actor_user_id, "reason": row.reason, "created_at": row.created_at.isoformat()} for row in rows])
