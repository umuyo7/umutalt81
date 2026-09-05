"""POS kimlik/yetki, masa, servis, adisyon ve audit temeli."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003_pos_foundation"
down_revision: Union[str, Sequence[str], None] = "0002_rename_catering_payments"
branch_labels = None
depends_on = None


def enum_column(*values: str, name: str):
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)
        return postgresql.ENUM(*values, name=name, create_type=False)
    return sa.Enum(*values, name=name)


def upgrade() -> None:
    permission_value_type = enum_column("BOOLEAN", "DECIMAL", name="permissionvaluetype")
    permission_effect = enum_column("ALLOW", "DENY", name="permissioneffect")
    service_status = enum_column("OPEN", "CHECK_REQUESTED", "PAYMENT_IN_PROGRESS", "CLOSED", name="servicestatus")
    check_status = enum_column("OPEN", "PARTIALLY_PAID", "PAID", "CLOSED", name="checkstatus")

    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(), nullable=True))

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_roles_code", "roles", ["code"], unique=True)

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("value_type", permission_value_type, nullable=False),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"], unique=True)

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), primary_key=True),
        sa.Column("assigned_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), primary_key=True),
        sa.Column("permission_id", sa.Integer(), sa.ForeignKey("permissions.id"), primary_key=True),
        sa.Column("effect", permission_effect, nullable=False),
        sa.Column("limit_value_numeric", sa.Numeric(12, 2), nullable=True),
        sa.Column("conditions_json", sa.JSON(), nullable=True),
    )
    op.create_table(
        "user_permissions",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("permission_id", sa.Integer(), sa.ForeignKey("permissions.id"), primary_key=True),
        sa.Column("effect", permission_effect, nullable=False),
        sa.Column("limit_value_numeric", sa.Numeric(12, 2), nullable=True),
        sa.Column("conditions_json", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "login_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_login_sessions_user_id", "login_sessions", ["user_id"])

    op.create_table(
        "table_sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "restaurant_tables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("table_sections.id"), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("section_id", "code", name="uq_restaurant_table_section_code"),
    )
    op.create_index("ix_restaurant_tables_section_id", "restaurant_tables", ["section_id"])
    op.create_index("ix_restaurant_tables_section_sort", "restaurant_tables", ["section_id", "sort_order"])

    op.create_table(
        "service_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("table_id", sa.Integer(), sa.ForeignKey("restaurant_tables.id"), nullable=False),
        sa.Column("primary_waiter_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("guest_count", sa.Integer(), nullable=False),
        sa.Column("operational_status", service_status, nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("opened_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("check_requested_at", sa.DateTime(), nullable=True),
        sa.Column("check_request_cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_service_sessions_table_id", "service_sessions", ["table_id"])
    op.create_index("ix_service_sessions_primary_waiter_id", "service_sessions", ["primary_waiter_id"])
    op.create_index("ix_service_sessions_operational_status", "service_sessions", ["operational_status"])
    op.create_index("ix_service_sessions_opened_at", "service_sessions", ["opened_at"])
    op.create_index(
        "ix_service_sessions_waiter_status_opened",
        "service_sessions",
        ["primary_waiter_id", "operational_status", "opened_at"],
    )
    op.create_index(
        "uq_service_sessions_active_table",
        "service_sessions",
        ["table_id"],
        unique=True,
        postgresql_where=sa.text("operational_status IN ('OPEN', 'CHECK_REQUESTED', 'PAYMENT_IN_PROGRESS')"),
        sqlite_where=sa.text("operational_status IN ('OPEN', 'CHECK_REQUESTED', 'PAYMENT_IN_PROGRESS')"),
    )

    op.create_table(
        "checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("check_number", sa.String(40), nullable=False),
        sa.Column("service_session_id", sa.Integer(), sa.ForeignKey("service_sessions.id"), nullable=False, unique=True),
        sa.Column("status", check_status, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("comp_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("final_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_due", sa.Numeric(12, 2), nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reopened_at", sa.DateTime(), nullable=True),
        sa.Column("reopened_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_checks_check_number", "checks", ["check_number"], unique=True)
    op.create_index("ix_checks_status", "checks", ["status"])
    op.create_index("ix_checks_opened_at", "checks", ["opened_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(80), nullable=False),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_actor_created", "audit_logs", ["actor_user_id", "created_at"])
    op.create_index("ix_audit_logs_entity_created", "audit_logs", ["entity_type", "entity_id", "created_at"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=True),
        sa.Column("resource_id", sa.String(80), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("scope", "actor_user_id", "idempotency_key", name="uq_idempotency_scope_actor_key"),
    )
    op.create_index("ix_idempotency_records_expires_at", "idempotency_records", ["expires_at"])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index("ix_outbox_events_occurred_at", "outbox_events", ["occurred_at"])
    op.create_index("ix_outbox_events_published_at", "outbox_events", ["published_at"])


def downgrade() -> None:
    for table in (
        "outbox_events",
        "idempotency_records",
        "audit_logs",
        "checks",
        "service_sessions",
        "restaurant_tables",
        "table_sections",
        "login_sessions",
        "user_permissions",
        "role_permissions",
        "user_roles",
        "permissions",
        "roles",
    ):
        op.drop_table(table)

    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
    op.drop_column("users", "is_active")

    for enum_type in (
        sa.Enum("OPEN", "PARTIALLY_PAID", "PAID", "CLOSED", name="checkstatus"),
        sa.Enum("OPEN", "CHECK_REQUESTED", "PAYMENT_IN_PROGRESS", "CLOSED", name="servicestatus"),
        sa.Enum("ALLOW", "DENY", name="permissioneffect"),
        sa.Enum("BOOLEAN", "DECIMAL", name="permissionvaluetype"),
    ):
        enum_type.drop(op.get_bind(), checkfirst=True)
