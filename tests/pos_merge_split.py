import tempfile
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import BusinessType, User
from app.permissions import seed_permissions
from app.pos_models import (
    Category,
    Check,
    CheckItem,
    CheckMerge,
    CheckSplit,
    CheckSplitMember,
    CheckStatus,
    Product,
    RestaurantTable,
    Role,
    ServiceSession,
    ServiceStatus,
    TableSection,
    UserRole,
)
from app.pos_services import add_item, merge_checks, open_service, split_check_to_table
from app.security import hash_password


with tempfile.TemporaryDirectory() as directory:
    engine = create_engine(f"sqlite:///{(Path(directory) / 'merge-split.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            seed_permissions(db)
            manager_role = db.scalar(select(Role).where(Role.code == "manager"))
            manager = User(name="Müdür", username="merge-manager", password_hash=hash_password("Manager-Merge-123!"), business_type=BusinessType.RESTAURANT)
            section = TableSection(name="Salon")
            category = Category(name="Yemek")
            db.add_all([manager, section, category]); db.flush()
            db.add(UserRole(user_id=manager.id, role_id=manager_role.id))
            tables = [RestaurantTable(section_id=section.id, code=str(index), display_name=f"Masa {index}", capacity=4) for index in range(1, 4)]
            product = Product(category_id=category.id, name="Köfte", price=Decimal("100.00"))
            db.add_all([*tables, product]); db.commit()

            service_a, check_a = open_service(db, manager.id, tables[0].id, 2)
            _, check_b = open_service(db, manager.id, tables[1].id, 2)
            db.commit()
            item_a = add_item(db, manager.id, check_a.id, product.id, Decimal("3"))
            add_item(db, manager.id, check_b.id, product.id, Decimal("2"))
            db.commit()

            merged = merge_checks(db, manager.id, check_a.id, check_b.id, "Masalar birlikte oturdu")
            db.commit(); db.refresh(merged); db.refresh(check_b)
            assert merged.final_total == Decimal("500.00")
            assert check_b.status == CheckStatus.CLOSED
            assert db.scalar(select(func.count(CheckMerge.id))) == 1

            target = split_check_to_table(db, manager.id, merged.id, tables[2].id, 1, {item_a.id: Decimal("1")}, "Bir misafir ayrıldı")
            db.commit(); db.refresh(merged); db.refresh(target)
            assert merged.final_total == Decimal("400.00")
            assert target.final_total == Decimal("100.00")
            assert db.scalar(select(func.count(CheckSplit.id))) == 1
            assert db.scalar(select(func.count(CheckSplitMember.id))) == 1
            target_service = db.get(ServiceSession, target.service_session_id)
            assert target_service.table_id == tables[2].id and target_service.operational_status == ServiceStatus.OPEN
            assert db.scalar(select(func.sum(CheckItem.quantity)).where(CheckItem.check_id == target.id)) == Decimal("1.000")
    finally:
        engine.dispose()

print("pos-merge-split-ok")
