from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .pos_models import (
    Permission,
    PermissionEffect,
    PermissionValueType,
    Role,
    RolePermission,
    UserPermission,
    UserRole,
)


PERMISSION_DEFINITIONS: dict[str, tuple[str, PermissionValueType]] = {
    "service.open": ("Boş masada servis açar.", PermissionValueType.BOOLEAN),
    "service.close": ("Servisi kapatır.", PermissionValueType.BOOLEAN),
    "service.change_guest_count": ("Kişi sayısını değiştirir.", PermissionValueType.BOOLEAN),
    "service.transfer_waiter": ("Garson devri yapar.", PermissionValueType.BOOLEAN),
    "service.move_table": ("Servisi başka masaya taşır.", PermissionValueType.BOOLEAN),
    "service.merge": ("Servis/adisyon birleştirir.", PermissionValueType.BOOLEAN),
    "service.split": ("Servis/adisyon böler.", PermissionValueType.BOOLEAN),
    "order.add_item": ("Adisyona ürün ekler.", PermissionValueType.BOOLEAN),
    "order.change_quantity": ("Ürün adedini değiştirir.", PermissionValueType.BOOLEAN),
    "order.cancel_item": ("Ürün kalemini iptal eder.", PermissionValueType.BOOLEAN),
    "order.change_price": ("Birim fiyatı değiştirir.", PermissionValueType.BOOLEAN),
    "order.comp_item": ("Ürün kalemini ikram yapar.", PermissionValueType.BOOLEAN),
    "discount.apply": ("İndirim uygular.", PermissionValueType.BOOLEAN),
    "discount.remove": ("İndirimi kaldırır.", PermissionValueType.BOOLEAN),
    "discount.override_limit": ("İndirim limitini aşar.", PermissionValueType.BOOLEAN),
    "discount.max_percent": ("Uygulanabilecek azami indirim yüzdesi.", PermissionValueType.DECIMAL),
    "payment.create": ("Açık adisyondan ödeme alır.", PermissionValueType.BOOLEAN),
    "payment.create_without_check_request": ("Hesap talebi olmadan ödeme alır.", PermissionValueType.BOOLEAN),
    "payment.reverse": ("Ödemeyi ters kayıtla iptal eder.", PermissionValueType.BOOLEAN),
    "payment.change_method": ("Ödeme yöntemini ters kayıtla düzeltir.", PermissionValueType.BOOLEAN),
    "payment.force_close": ("Farkla adisyon kapatır.", PermissionValueType.BOOLEAN),
    "payment.close_check": ("Bakiyesi tamamlanan adisyonu kapatır.", PermissionValueType.BOOLEAN),
    "check.request": ("Hesap talebi oluşturur.", PermissionValueType.BOOLEAN),
    "check.cancel_request": ("Hesap talebini geri alır.", PermissionValueType.BOOLEAN),
    "check.reopen": ("Kapalı adisyonu yeniden açar.", PermissionValueType.BOOLEAN),
    "reports.view": ("Raporları görüntüler.", PermissionValueType.BOOLEAN),
    "reports.export": ("Raporları dışa aktarır.", PermissionValueType.BOOLEAN),
    "shift.open": ("Kasa vardiyası açar.", PermissionValueType.BOOLEAN),
    "shift.close": ("Kasa vardiyasını kapatır ve Z özeti alır.", PermissionValueType.BOOLEAN),
    "users.manage": ("Kullanıcı ve rol yönetir.", PermissionValueType.BOOLEAN),
    "products.manage": ("Ürün ve kategori yönetir.", PermissionValueType.BOOLEAN),
    "tables.manage": ("Salon ve masa yönetir.", PermissionValueType.BOOLEAN),
    "settings.manage": ("Sistem ayarlarını yönetir.", PermissionValueType.BOOLEAN),
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "waiter": {
        "service.open", "service.close", "service.change_guest_count", "order.add_item", "order.change_quantity",
        "check.request", "discount.max_percent",
    },
    "head_waiter": {
        "service.open", "service.change_guest_count", "service.transfer_waiter", "service.move_table",
        "order.add_item", "order.change_quantity", "order.cancel_item", "discount.apply", "discount.remove",
        "check.request", "check.cancel_request", "discount.max_percent",
    },
    "cashier": {
        "service.open", "service.close", "service.change_guest_count", "order.add_item", "order.change_quantity",
        "check.request", "payment.create", "payment.create_without_check_request", "payment.close_check",
        "discount.max_percent",
    },
    "manager": set(PERMISSION_DEFINITIONS),
    "admin": set(PERMISSION_DEFINITIONS),
}

ROLE_LIMITS: dict[str, dict[str, Decimal]] = {
    "waiter": {"discount.max_percent": Decimal("0")},
    "head_waiter": {"discount.max_percent": Decimal("10")},
    "cashier": {"discount.max_percent": Decimal("0")},
    "manager": {"discount.max_percent": Decimal("100")},
    "admin": {"discount.max_percent": Decimal("100")},
}


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    limit: Decimal | None = None


def seed_permissions(db: Session) -> None:
    existing_permissions = {row.code: row for row in db.scalars(select(Permission)).all()}
    for code, (description, value_type) in PERMISSION_DEFINITIONS.items():
        if code not in existing_permissions:
            permission = Permission(code=code, description=description, value_type=value_type)
            db.add(permission)
            existing_permissions[code] = permission

    existing_roles = {row.code: row for row in db.scalars(select(Role)).all()}
    for code in ROLE_PERMISSIONS:
        if code not in existing_roles:
            role = Role(code=code, name=code.replace("_", " ").title(), is_system=True, is_active=True)
            db.add(role)
            existing_roles[code] = role
    db.flush()

    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        role = existing_roles[role_code]
        current = {
            row.permission_id
            for row in db.scalars(select(RolePermission).where(RolePermission.role_id == role.id)).all()
        }
        for permission_code in permission_codes:
            permission = existing_permissions[permission_code]
            if permission.id not in current:
                db.add(
                    RolePermission(
                        role_id=role.id,
                        permission_id=permission.id,
                        effect=PermissionEffect.ALLOW,
                        limit_value_numeric=ROLE_LIMITS.get(role_code, {}).get(permission_code),
                    )
                )
    db.flush()


def sync_role_permissions(db: Session) -> None:
    """Remove RolePermission rows for (role, permission) pairs no longer granted
    in ROLE_PERMISSIONS. seed_permissions() only ever adds missing grants; this
    cleans up grants that were removed from the source-of-truth dict above so a
    running deployment doesn't keep stale permissions after a role matrix change.
    Only touches roles that exist in ROLE_PERMISSIONS (i.e. system roles)."""
    existing_permissions = {row.code: row for row in db.scalars(select(Permission)).all()}
    existing_roles = {row.code: row for row in db.scalars(select(Role)).all()}

    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        role = existing_roles.get(role_code)
        if role is None:
            continue
        allowed_permission_ids = {
            existing_permissions[code].id for code in permission_codes if code in existing_permissions
        }
        stale = db.scalars(
            select(RolePermission).where(
                RolePermission.role_id == role.id,
                RolePermission.permission_id.notin_(allowed_permission_ids),
            )
        ).all()
        for row in stale:
            db.delete(row)
    db.flush()


def permission_decision(db: Session, user_id: int, permission_code: str, now: datetime | None = None) -> PermissionDecision:
    now = now or datetime.utcnow()
    permission = db.scalar(select(Permission).where(Permission.code == permission_code))
    if permission is None:
        return PermissionDecision(False)

    user_override = db.scalar(
        select(UserPermission).where(
            UserPermission.user_id == user_id,
            UserPermission.permission_id == permission.id,
        )
    )
    if user_override is not None and (user_override.expires_at is None or user_override.expires_at > now):
        return PermissionDecision(
            user_override.effect == PermissionEffect.ALLOW,
            Decimal(user_override.limit_value_numeric) if user_override.limit_value_numeric is not None else None,
        )

    grants = db.execute(
        select(RolePermission.effect, RolePermission.limit_value_numeric)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.user_id == user_id,
            RolePermission.permission_id == permission.id,
            Role.is_active.is_(True),
        )
    ).all()
    if any(effect == PermissionEffect.DENY for effect, _ in grants):
        return PermissionDecision(False)
    allowed_limits = [Decimal(limit) for effect, limit in grants if effect == PermissionEffect.ALLOW and limit is not None]
    allowed = any(effect == PermissionEffect.ALLOW for effect, _ in grants)
    return PermissionDecision(allowed, max(allowed_limits) if allowed_limits else None)


def require_permission(db: Session, user_id: int, permission_code: str) -> PermissionDecision:
    decision = permission_decision(db, user_id, permission_code)
    if not decision.allowed:
        raise PermissionError(f"Bu işlem için {permission_code} yetkisi bulunmuyor.")
    return decision
