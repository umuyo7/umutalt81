import os
import tempfile
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


with tempfile.TemporaryDirectory() as directory:
    database = Path(directory) / "migration.db"
    database_url = f"sqlite:///{database.as_posix()}"
    os.environ["DATABASE_URL"] = database_url

    config = Config("alembic.ini")
    command.upgrade(config, "0001_existing_schema_baseline")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, name, username, password_hash, business_type, created_at) "
                "VALUES (1, 'Catering', 'catering', 'hash', 'CATERING', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO customers "
                "(id, user_id, company_name, contact_name, phone, email, address, meal_price, "
                "overtime_price, default_people, invoice_customer, carried_debt, active) "
                "VALUES (1, 1, 'Test', '', '', '', '', 10, 0, 1, 0, 0, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO payments (id, customer_id, payment_date, amount, note) "
                "VALUES (1, 1, '2026-09-04', 125.50, 'korunmalı')"
            )
        )

    command.upgrade(config, "head")

    try:
        tables = set(inspect(engine).get_table_names())
        assert "catering_payments" in tables
        assert "payments" in tables  # Yeni POS adisyon ödemeleri tablosu.
        assert {"roles", "permissions", "restaurant_tables", "service_sessions", "checks", "audit_logs", "shifts"} <= tables
        assert {"sent_to_kitchen_at", "sent_to_kitchen_by_user_id", "tax_rate_snapshot"} <= {column["name"] for column in inspect(engine).get_columns("check_items")}
        assert "shift_id" in {column["name"] for column in inspect(engine).get_columns("payments")}
        with engine.connect() as connection:
            row = connection.execute(text("SELECT amount, note FROM catering_payments WHERE id = 1")).one()
            assert Decimal(str(row.amount)).quantize(Decimal("0.01")) == Decimal("125.50")
            assert row.note == "korunmalı"
    finally:
        engine.dispose()

print("migration-smoke-ok")
