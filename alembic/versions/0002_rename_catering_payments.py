"""Catering tahsilatlarını POS ödemelerinden isim olarak ayır."""

from typing import Sequence, Union

from alembic import op


revision: str = "0002_rename_catering_payments"
down_revision: Union[str, Sequence[str], None] = "0001_existing_schema_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("payments", "catering_payments")
    op.drop_index("ix_payments_customer_id", table_name="catering_payments")
    op.drop_index("ix_payments_payment_date", table_name="catering_payments")
    op.create_index("ix_catering_payments_customer_id", "catering_payments", ["customer_id"])
    op.create_index("ix_catering_payments_payment_date", "catering_payments", ["payment_date"])


def downgrade() -> None:
    op.drop_index("ix_catering_payments_customer_id", table_name="catering_payments")
    op.drop_index("ix_catering_payments_payment_date", table_name="catering_payments")
    op.rename_table("catering_payments", "payments")
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.create_index("ix_payments_payment_date", "payments", ["payment_date"])
