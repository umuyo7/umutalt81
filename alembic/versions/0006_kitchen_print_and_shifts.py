"""Mutfak gönderim takibi ve kasa vardiyaları."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_kitchen_print_and_shifts"
down_revision: Union[str, Sequence[str], None] = "0005_check_merge_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opened_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("opening_cash_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("closed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("closing_cash_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("expected_cash_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("cash_difference", sa.Numeric(12, 2), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_shifts_opened_by_user_id", "shifts", ["opened_by_user_id"])
    op.create_index("ix_shifts_opened_at", "shifts", ["opened_at"])
    op.create_index("ix_shifts_closed_at", "shifts", ["closed_at"])

    with op.batch_alter_table("check_items") as batch:
        batch.add_column(sa.Column("tax_rate_snapshot", sa.Numeric(5, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("sent_to_kitchen_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("sent_to_kitchen_by_user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_check_items_sent_to_kitchen_by_user_id_users",
            "users", ["sent_to_kitchen_by_user_id"], ["id"],
        )
        batch.create_index("ix_check_items_sent_to_kitchen_at", ["sent_to_kitchen_at"])

    with op.batch_alter_table("payments") as batch:
        batch.add_column(sa.Column("shift_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_payments_shift_id_shifts", "shifts", ["shift_id"], ["id"])
        batch.create_index("ix_payments_shift_id", ["shift_id"])


def downgrade() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.drop_index("ix_payments_shift_id")
        batch.drop_constraint("fk_payments_shift_id_shifts", type_="foreignkey")
        batch.drop_column("shift_id")
    with op.batch_alter_table("check_items") as batch:
        batch.drop_index("ix_check_items_sent_to_kitchen_at")
        batch.drop_constraint("fk_check_items_sent_to_kitchen_by_user_id_users", type_="foreignkey")
        batch.drop_column("sent_to_kitchen_by_user_id")
        batch.drop_column("sent_to_kitchen_at")
        batch.drop_column("tax_rate_snapshot")
    op.drop_index("ix_shifts_closed_at", table_name="shifts")
    op.drop_index("ix_shifts_opened_at", table_name="shifts")
    op.drop_index("ix_shifts_opened_by_user_id", table_name="shifts")
    op.drop_table("shifts")
