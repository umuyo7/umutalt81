"""Günün menüsü (daily menu) izni ekler (data migration).

cashier: menu.daily_manage eklenir (kasiyer günün menüsü kısayollarını seçebilir).
Yeni permission tanımı manager/admin'e zaten tam yetki setinden otomatik dahil olur.

Şema değişikliği yok; sadece roles/permissions/role_permissions satırları
app/permissions.py içindeki güncel ROLE_PERMISSIONS sözlüğüyle senkronize edilir.
seed_permissions() eksik izinleri ekler, sync_role_permissions() ise artık
ROLE_PERMISSIONS'ta olmayan role_permissions satırlarını siler.
"""

from typing import Sequence, Union

from sqlalchemy.orm import Session

from alembic import op

revision: str = "0008_daily_menu_permission"
down_revision: Union[str, Sequence[str], None] = "0007_role_matrix_update"
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
    from sqlalchemy import select

    from app.pos_models import Permission, Role, RolePermission

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        permission = session.scalar(select(Permission).where(Permission.code == "menu.daily_manage"))
        role = session.scalar(select(Role).where(Role.code == "cashier"))
        if permission is not None and role is not None:
            grant = session.scalar(
                select(RolePermission).where(RolePermission.role_id == role.id, RolePermission.permission_id == permission.id)
            )
            if grant is not None:
                session.delete(grant)
        session.commit()
    finally:
        session.close()
