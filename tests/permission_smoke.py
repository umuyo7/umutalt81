import tempfile
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import BusinessType, User
from app.permissions import permission_decision, seed_permissions
from app.pos_models import Permission, PermissionEffect, Role, UserPermission, UserRole
from app.security import hash_password


with tempfile.TemporaryDirectory() as directory:
    engine = create_engine(f"sqlite:///{(Path(directory) / 'permission.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            cashier = User(
                name="Kasa",
                username="cashier",
                password_hash=hash_password("Cashier-Test-123!"),
                business_type=BusinessType.RESTAURANT,
            )
            db.add(cashier)
            seed_permissions(db)
            db.flush()

            cashier_role = db.scalar(select(Role).where(Role.code == "cashier"))
            assert cashier_role is not None
            db.add(UserRole(user_id=cashier.id, role_id=cashier_role.id))
            db.commit()

            assert permission_decision(db, cashier.id, "payment.create").allowed
            assert permission_decision(db, cashier.id, "payment.create_without_check_request").allowed
            assert permission_decision(db, cashier.id, "shift.open").allowed
            assert permission_decision(db, cashier.id, "shift.close").allowed
            assert not permission_decision(db, cashier.id, "service.open").allowed
            discount_limit = permission_decision(db, cashier.id, "discount.max_percent")
            assert discount_limit.allowed and discount_limit.limit == Decimal("0.00")

            permission = db.scalar(select(Permission).where(Permission.code == "payment.create_without_check_request"))
            assert permission is not None
            db.add(
                UserPermission(
                    user_id=cashier.id,
                    permission_id=permission.id,
                    effect=PermissionEffect.DENY,
                )
            )
            db.commit()
            assert not permission_decision(db, cashier.id, "payment.create_without_check_request").allowed
            assert permission_decision(db, cashier.id, "payment.create").allowed
    finally:
        engine.dispose()

print("permission-smoke-ok")
