"""Mevcut FastAPI/PostgreSQL şemasının Alembic başlangıç noktası.

Canlıda mevcut tablolar varsa bu revision çalıştırılmaz; önce
`alembic stamp 0001_existing_schema_baseline` uygulanır.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_existing_schema_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels = None
depends_on = None


def enum_column(*values: str, name: str):
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)
        return postgresql.ENUM(*values, name=name, create_type=False)
    return sa.Enum(*values, name=name)


def upgrade() -> None:
    business_type = enum_column("CATERING", "RESTAURANT", name="businesstype")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("business_type", business_type, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("company_name", sa.String(160), nullable=False),
        sa.Column("contact_name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("email", sa.String(190), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("meal_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("overtime_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("default_people", sa.Integer(), nullable=False),
        sa.Column("invoice_customer", sa.Boolean(), nullable=False),
        sa.Column("carried_debt", sa.Numeric(12, 2), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_customers_user_id", "customers", ["user_id"])

    op.create_table(
        "daily_meals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("meal_count", sa.Integer(), nullable=False),
        sa.Column("overtime_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("customer_id", "entry_date", name="uq_daily_meal_customer_date"),
    )
    op.create_index("ix_daily_meals_customer_id", "daily_meals", ["customer_id"])
    op.create_index("ix_daily_meals_entry_date", "daily_meals", ["entry_date"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.String(255), nullable=False),
    )
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.create_index("ix_payments_payment_date", "payments", ["payment_date"])

    op.create_table(
        "restaurant_revenues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revenue_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.String(255), nullable=False),
        sa.UniqueConstraint("user_id", "revenue_date", name="uq_restaurant_revenue_date"),
    )
    op.create_index("ix_restaurant_revenues_revenue_date", "restaurant_revenues", ["revenue_date"])
    op.create_index("ix_restaurant_revenues_user_id", "restaurant_revenues", ["user_id"])

    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
    )
    op.create_index("ix_expenses_expense_date", "expenses", ["expense_date"])
    op.create_index("ix_expenses_user_id", "expenses", ["user_id"])

    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("role", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("monthly_salary", sa.Numeric(12, 2), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_employees_user_id", "employees", ["user_id"])

    op.create_table(
        "salary_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("period", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.String(255), nullable=False),
    )
    op.create_index("ix_salary_payments_employee_id", "salary_payments", ["employee_id"])
    op.create_index("ix_salary_payments_payment_date", "salary_payments", ["payment_date"])

    op.create_table(
        "condolence_meals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("company_name", sa.String(160), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
    )
    op.create_index("ix_condolence_meals_entry_date", "condolence_meals", ["entry_date"])
    op.create_index("ix_condolence_meals_user_id", "condolence_meals", ["user_id"])

    op.create_table(
        "legacy_statements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("legacy_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_legacy_statements_customer_id", "legacy_statements", ["customer_id"])
    op.create_index("ix_legacy_statements_user_id", "legacy_statements", ["user_id"])

    op.create_table(
        "legacy_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
    )
    op.create_index("ix_legacy_imports_source_sha256", "legacy_imports", ["source_sha256"], unique=True)


def downgrade() -> None:
    for table in (
        "legacy_imports",
        "legacy_statements",
        "condolence_meals",
        "salary_payments",
        "employees",
        "expenses",
        "restaurant_revenues",
        "payments",
        "daily_meals",
        "customers",
        "users",
    ):
        op.drop_table(table)
    sa.Enum("CATERING", "RESTAURANT", name="businesstype").drop(op.get_bind(), checkfirst=True)
