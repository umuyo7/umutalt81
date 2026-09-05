import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class PermissionEffect(str, enum.Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class PermissionValueType(str, enum.Enum):
    BOOLEAN = "BOOLEAN"
    DECIMAL = "DECIMAL"


class ServiceStatus(str, enum.Enum):
    OPEN = "OPEN"
    CHECK_REQUESTED = "CHECK_REQUESTED"
    PAYMENT_IN_PROGRESS = "PAYMENT_IN_PROGRESS"
    CLOSED = "CLOSED"


class CheckStatus(str, enum.Enum):
    OPEN = "OPEN"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    CLOSED = "CLOSED"


class DiscountType(str, enum.Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"


class DiscountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REMOVED = "REMOVED"


class PaymentMethod(str, enum.Enum):
    CASH = "CASH"
    CREDIT_CARD = "CREDIT_CARD"
    MEAL_CARD = "MEAL_CARD"
    BANK_TRANSFER = "BANK_TRANSFER"
    OTHER = "OTHER"


class PaymentStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    REVERSED = "REVERSED"


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255))
    value_type: Mapped[PermissionValueType] = mapped_column(Enum(PermissionValueType), default=PermissionValueType.BOOLEAN)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    assigned_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"), primary_key=True)
    effect: Mapped[PermissionEffect] = mapped_column(Enum(PermissionEffect), default=PermissionEffect.ALLOW)
    limit_value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    conditions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class UserPermission(Base):
    __tablename__ = "user_permissions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"), primary_key=True)
    effect: Mapped[PermissionEffect] = mapped_column(Enum(PermissionEffect), default=PermissionEffect.ALLOW)
    limit_value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    conditions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TableSection(Base):
    __tablename__ = "table_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RestaurantTable(Base):
    __tablename__ = "restaurant_tables"
    __table_args__ = (
        UniqueConstraint("section_id", "code", name="uq_restaurant_table_section_code"),
        Index("ix_restaurant_tables_section_sort", "section_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("table_sections.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    display_name: Mapped[str] = mapped_column(String(120))
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ServiceSession(Base):
    __tablename__ = "service_sessions"
    __table_args__ = (
        Index("ix_service_sessions_waiter_status_opened", "primary_waiter_id", "operational_status", "opened_at"),
        Index(
            "uq_service_sessions_active_table",
            "table_id",
            unique=True,
            postgresql_where=text("operational_status IN ('OPEN', 'CHECK_REQUESTED', 'PAYMENT_IN_PROGRESS')"),
            sqlite_where=text("operational_status IN ('OPEN', 'CHECK_REQUESTED', 'PAYMENT_IN_PROGRESS')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("restaurant_tables.id"), index=True)
    primary_waiter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    guest_count: Mapped[int] = mapped_column(Integer)
    operational_status: Mapped[ServiceStatus] = mapped_column(Enum(ServiceStatus), default=ServiceStatus.OPEN, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    opened_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    check_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    check_request_cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Check(Base):
    __tablename__ = "checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    check_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    service_session_id: Mapped[int] = mapped_column(ForeignKey("service_sessions.id"), unique=True)
    status: Mapped[CheckStatus] = mapped_column(Enum(CheckStatus), default=CheckStatus.OPEN, index=True)
    currency: Mapped[str] = mapped_column(String(3), default="TRY")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    discount_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    comp_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    final_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    paid_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    balance_due: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reopened_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_products_price_nonnegative"),
        Index("ix_products_category_sort", "category_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    sku: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class CheckItem(Base):
    __tablename__ = "check_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_check_items_quantity_positive"),
        Index("ix_check_items_check_created", "check_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    product_name_snapshot: Mapped[str] = mapped_column(String(160))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    tax_rate_snapshot: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_to_kitchen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    sent_to_kitchen_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_comp: Mapped[bool] = mapped_column(Boolean, default=False)
    comp_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    comp_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    comp_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    price_override: Mapped[bool] = mapped_column(Boolean, default=False)
    original_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_overridden_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Discount(Base):
    __tablename__ = "discounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), index=True)
    discount_type: Mapped[DiscountType] = mapped_column(Enum(DiscountType))
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    calculated_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[DiscountStatus] = mapped_column(Enum(DiscountStatus), default=DiscountStatus.ACTIVE)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    removed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    removal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    opened_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    opening_cash_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    closing_cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    expected_cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cash_difference: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        Index("ix_payments_check_status_created", "check_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), index=True)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"), nullable=True, index=True)
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.COMPLETED)
    check_status_snapshot: Mapped[str] = mapped_column(String(40))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    reversed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reverses_payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ServiceWaiterTransfer(Base):
    __tablename__ = "service_waiter_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_session_id: Mapped[int] = mapped_column(ForeignKey("service_sessions.id"), index=True)
    from_waiter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    to_waiter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TableTransfer(Base):
    __tablename__ = "table_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_session_id: Mapped[int] = mapped_column(ForeignKey("service_sessions.id"), index=True)
    from_table_id: Mapped[int] = mapped_column(ForeignKey("restaurant_tables.id"))
    to_table_id: Mapped[int] = mapped_column(ForeignKey("restaurant_tables.id"))
    reason: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ForceCloseAdjustment(Base):
    __tablename__ = "force_close_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), index=True)
    expected_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    difference_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CheckMerge(Base):
    __tablename__ = "check_merges"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), index=True)
    source_check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CheckSplit(Base):
    __tablename__ = "check_splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), index=True)
    target_check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CheckSplitMember(Base):
    __tablename__ = "check_split_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    check_split_id: Mapped[int] = mapped_column(ForeignKey("check_splits.id"), index=True)
    source_item_id: Mapped[int] = mapped_column(ForeignKey("check_items.id"))
    target_item_id: Mapped[int] = mapped_column(ForeignKey("check_items.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
        Index("ix_audit_logs_entity_created", "entity_type", "entity_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80))
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("scope", "actor_user_id", "idempotency_key", name="uq_idempotency_scope_actor_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(80))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
