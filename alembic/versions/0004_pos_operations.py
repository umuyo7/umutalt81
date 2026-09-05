"""Ürün, adisyon kalemi, indirim ve POS ödeme şeması."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004_pos_operations"
down_revision: Union[str, Sequence[str], None] = "0003_pos_foundation"
branch_labels = None
depends_on = None


def enum_column(*values: str, name: str):
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)
        return postgresql.ENUM(*values, name=name, create_type=False)
    return sa.Enum(*values, name=name)


def upgrade() -> None:
    discount_type = enum_column("PERCENTAGE", "FIXED_AMOUNT", name="discounttype")
    discount_status = enum_column("ACTIVE", "REMOVED", name="discountstatus")
    payment_method = enum_column("CASH", "CREDIT_CARD", "MEAL_CARD", "BANK_TRANSFER", "OTHER", name="paymentmethod")
    payment_status = enum_column("COMPLETED", "REVERSED", name="paymentstatus")

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("sku", sa.String(80), nullable=True, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_favorite", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("price >= 0", name="ck_products_price_nonnegative"),
    )
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_name", "products", ["name"])
    op.create_index("ix_products_category_sort", "products", ["category_id", "sort_order"])

    op.create_table(
        "check_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("check_id", sa.Integer(), sa.ForeignKey("checks.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("product_name_snapshot", sa.String(160), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("is_cancelled", sa.Boolean(), nullable=False),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("is_comp", sa.Boolean(), nullable=False),
        sa.Column("comp_reason", sa.Text(), nullable=True),
        sa.Column("comp_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("comp_at", sa.DateTime(), nullable=True),
        sa.Column("price_override", sa.Boolean(), nullable=False),
        sa.Column("original_unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_override_reason", sa.Text(), nullable=True),
        sa.Column("price_overridden_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_check_items_quantity_positive"),
    )
    op.create_index("ix_check_items_check_id", "check_items", ["check_id"])
    op.create_index("ix_check_items_check_created", "check_items", ["check_id", "created_at"])

    op.create_table(
        "discounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("check_id", sa.Integer(), sa.ForeignKey("checks.id"), nullable=False),
        sa.Column("discount_type", discount_type, nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=False),
        sa.Column("calculated_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", discount_status, nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("removed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("removed_at", sa.DateTime(), nullable=True),
        sa.Column("removal_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_discounts_check_id", "discounts", ["check_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("check_id", sa.Integer(), sa.ForeignKey("checks.id"), nullable=False),
        sa.Column("payment_method", payment_method, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("check_status_snapshot", sa.String(40), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reversed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reversed_at", sa.DateTime(), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.Column("reverses_payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("external_reference", sa.String(160), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
    )
    op.create_index("ix_payments_check_id", "payments", ["check_id"])
    op.create_index("ix_payments_created_by_user_id", "payments", ["created_by_user_id"])
    op.create_index("ix_payments_created_at", "payments", ["created_at"])
    op.create_index("ix_payments_check_status_created", "payments", ["check_id", "status", "created_at"])

    op.create_table(
        "service_waiter_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_session_id", sa.Integer(), sa.ForeignKey("service_sessions.id"), nullable=False),
        sa.Column("from_waiter_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("to_waiter_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_service_waiter_transfers_service_session_id", "service_waiter_transfers", ["service_session_id"])

    op.create_table(
        "table_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_session_id", sa.Integer(), sa.ForeignKey("service_sessions.id"), nullable=False),
        sa.Column("from_table_id", sa.Integer(), sa.ForeignKey("restaurant_tables.id"), nullable=False),
        sa.Column("to_table_id", sa.Integer(), sa.ForeignKey("restaurant_tables.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_table_transfers_service_session_id", "table_transfers", ["service_session_id"])

    op.create_table(
        "force_close_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("check_id", sa.Integer(), sa.ForeignKey("checks.id"), nullable=False),
        sa.Column("expected_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("difference_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_force_close_adjustments_check_id", "force_close_adjustments", ["check_id"])


def downgrade() -> None:
    for table in (
        "force_close_adjustments",
        "table_transfers",
        "service_waiter_transfers",
        "payments",
        "discounts",
        "check_items",
        "products",
        "categories",
    ):
        op.drop_table(table)
    for enum_type in (
        sa.Enum("COMPLETED", "REVERSED", name="paymentstatus"),
        sa.Enum("CASH", "CREDIT_CARD", "MEAL_CARD", "BANK_TRANSFER", "OTHER", name="paymentmethod"),
        sa.Enum("ACTIVE", "REMOVED", name="discountstatus"),
        sa.Enum("PERCENTAGE", "FIXED_AMOUNT", name="discounttype"),
    ):
        enum_type.drop(op.get_bind(), checkfirst=True)
