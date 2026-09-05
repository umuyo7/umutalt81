"""Adisyon birleştirme ve bölme geçmişi."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_check_merge_split"
down_revision: Union[str, Sequence[str], None] = "0004_pos_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "check_merges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_check_id", sa.Integer(), sa.ForeignKey("checks.id"), nullable=False),
        sa.Column("source_check_id", sa.Integer(), sa.ForeignKey("checks.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_check_merges_target_check_id", "check_merges", ["target_check_id"])
    op.create_index("ix_check_merges_source_check_id", "check_merges", ["source_check_id"])
    op.create_table(
        "check_splits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_check_id", sa.Integer(), sa.ForeignKey("checks.id"), nullable=False),
        sa.Column("target_check_id", sa.Integer(), sa.ForeignKey("checks.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_check_splits_source_check_id", "check_splits", ["source_check_id"])
    op.create_index("ix_check_splits_target_check_id", "check_splits", ["target_check_id"])
    op.create_table(
        "check_split_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("check_split_id", sa.Integer(), sa.ForeignKey("check_splits.id"), nullable=False),
        sa.Column("source_item_id", sa.Integer(), sa.ForeignKey("check_items.id"), nullable=False),
        sa.Column("target_item_id", sa.Integer(), sa.ForeignKey("check_items.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
    )
    op.create_index("ix_check_split_members_check_split_id", "check_split_members", ["check_split_id"])


def downgrade() -> None:
    op.drop_table("check_split_members")
    op.drop_table("check_splits")
    op.drop_table("check_merges")
