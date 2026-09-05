import enum
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class BusinessType(str, enum.Enum):
    CATERING = "catering"
    RESTAURANT = "restaurant"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    business_type: Mapped[BusinessType] = mapped_column(Enum(BusinessType))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    company_name: Mapped[str] = mapped_column(String(160))
    contact_name: Mapped[str] = mapped_column(String(160), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(190), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    meal_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    overtime_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    default_people: Mapped[int] = mapped_column(Integer, default=0)
    invoice_customer: Mapped[bool] = mapped_column(Boolean, default=False)
    carried_debt: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DailyMeal(Base):
    __tablename__ = "daily_meals"
    __table_args__ = (UniqueConstraint("customer_id", "entry_date", name="uq_daily_meal_customer_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    meal_count: Mapped[int] = mapped_column(Integer, default=0)
    overtime_count: Mapped[int] = mapped_column(Integer, default=0)


class CateringPayment(Base):
    """Catering müşteri tahsilatı; POS adisyon ödemesi değildir."""

    __tablename__ = "catering_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    note: Mapped[str] = mapped_column(String(255), default="")


class RestaurantRevenue(Base):
    __tablename__ = "restaurant_revenues"
    __table_args__ = (UniqueConstraint("user_id", "revenue_date", name="uq_restaurant_revenue_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    revenue_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    note: Mapped[str] = mapped_column(String(255), default="")


class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    monthly_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SalaryPayment(Base):
    __tablename__ = "salary_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    period: Mapped[str] = mapped_column(String(30), default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    note: Mapped[str] = mapped_column(String(255), default="")


class CondolenceMeal(Base):
    """Eski sistemdeki taziye yemeği kayıtlarını kayıpsız saklar."""

    __tablename__ = "condolence_meals"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    company_name: Mapped[str] = mapped_column(String(160), default="")
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    note: Mapped[str] = mapped_column(Text, default="")


class LegacyStatement(Base):
    """Eski ekstre anlık görüntülerinin ham kopyası."""

    __tablename__ = "legacy_statements"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    legacy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)


class LegacyImport(Base):
    __tablename__ = "legacy_imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    counts: Mapped[dict] = mapped_column(JSON)
