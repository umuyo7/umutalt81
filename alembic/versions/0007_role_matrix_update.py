"""Garson/kasiyer/yönetici rol matrisini günceller (data migration).

waiter: service.close eklenir.
cashier: service.*/order.*/check.request eklenir; reports.view, shift.open,
         shift.close kaldırılır.
manager: users.manage ve settings.manage eklenir (artık admin ile aynı tam yetki).

Şema değişikliği yok; sadece roles/permissions/role_permissions satırları
app/permissions.py içindeki güncel ROLE_PERMISSIONS sözlüğüyle senkronize edilir.
seed_permissions() eksik izinleri ekler, sync_role_permissions() ise artık
ROLE_PERMISSIONS'ta olmayan role_permissions satırlarını siler.
"""

from typing import Sequence, Union

from sqlalchemy.orm import Session

from alembic import op

revision: str = "0007_role_matrix_update"
down_revision: Union[str, Sequence[str], None] = "0006_kitchen_print_and_shifts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.permissions import seed_permissions, sync_role_permissions

    bind = op.get_bind()
    session = Session(bind=bind)
    seed_permissions(session)
    sync_role_permissions(session)
    session.commit()


def downgrade() -> None:
    # Rol matrisi bir öncesi (Faz 1) haline döndürülür. seed_permissions ile
    # eklenen Permission/Role satırları başka veriyle bağlı olabileceğinden
    # silinmez; sadece role_permissions grant'leri eski matrise göre yeniden
    # kurulur.
    from sqlalchemy import select

    from app.pos_models import Permission, PermissionEffect, Role, RolePermission

    previous_role_permissions: dict[str, set[str]] = {
        "waiter": {
            "service.open", "service.change_guest_count", "order.add_item", "order.change_quantity",
            "check.request", "discount.max_percent",
        },
        "cashier": {
            "payment.create", "payment.create_without_check_request", "payment.close_check", "reports.view",
            "shift.open", "shift.close", "discount.max_percent",
        },
        "manager": None,  # set(PERMISSION_DEFINITIONS) - {"users.manage", "settings.manage"}, resolved below
    }

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        permissions = {row.code: row for row in session.scalars(select(Permission)).all()}
        roles = {row.code: row for row in session.scalars(select(Role)).all()}
        previous_role_permissions["manager"] = set(permissions) - {"users.manage", "settings.manage"}

        for role_code, permission_codes in previous_role_permissions.items():
            role = roles.get(role_code)
            if role is None or permission_codes is None:
                continue
            allowed_ids = {permissions[code].id for code in permission_codes if code in permissions}
            current = {
                row.permission_id: row
                for row in session.scalars(
                    select(RolePermission).where(RolePermission.role_id == role.id)
                ).all()
            }
            for permission_id, row in current.items():
                if permission_id not in allowed_ids:
                    session.delete(row)
            for permission_id in allowed_ids:
                if permission_id not in current:
                    session.add(
                        RolePermission(role_id=role.id, permission_id=permission_id, effect=PermissionEffect.ALLOW)
                    )
        session.commit()
    finally:
        session.close()
