import tempfile
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import BusinessType, User
from app.permissions import seed_permissions
from app.pos_models import Category, CheckItem, Product, RestaurantTable, Role, TableSection, UserRole
from app.pos_services import PosError, add_item, open_service, send_to_kitchen


with tempfile.TemporaryDirectory() as directory:
    engine = create_engine(f"sqlite:///{(Path(directory) / 'kitchen.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            seed_permissions(db)
            waiter_role = db.scalar(select(Role).where(Role.code == "waiter"))
            waiter = User(name="Garson", username="kitchen-waiter", password_hash="test", business_type=BusinessType.RESTAURANT)
            section, category = TableSection(name="Salon"), Category(name="Yemek")
            db.add_all([waiter, section, category]); db.flush()
            db.add(UserRole(user_id=waiter.id, role_id=waiter_role.id))
            table = RestaurantTable(section_id=section.id, code="K1", display_name="Masa K1", capacity=4)
            product = Product(category_id=category.id, name="Köfte", price=Decimal("240.00"), tax_rate=Decimal("10.00"))
            db.add_all([table, product]); db.commit()

            _, check = open_service(db, waiter.id, table.id, 2)
            first = add_item(db, waiter.id, check.id, product.id, Decimal("2"), "Soğansız")
            db.commit()
            _, _, sent, sent_at = send_to_kitchen(db, waiter.id, table.id)
            db.commit()
            assert [row.id for row in sent] == [first.id]
            assert first.sent_to_kitchen_at == sent_at and first.sent_to_kitchen_by_user_id == waiter.id
            assert first.tax_rate_snapshot == Decimal("10.00")
            try:
                send_to_kitchen(db, waiter.id, table.id)
            except PosError as exc:
                db.rollback(); assert exc.code == "NO_UNSENT_ITEMS"
            else:
                raise AssertionError("Aynı kalem ikinci kez mutfağa gönderilmemeliydi")
            second = add_item(db, waiter.id, check.id, product.id)
            db.commit()
            _, _, sent, _ = send_to_kitchen(db, waiter.id, table.id)
            assert [row.id for row in sent] == [second.id]
            assert db.scalar(select(CheckItem.sent_to_kitchen_at).where(CheckItem.id == first.id)) is not None
    finally:
        engine.dispose()

print("kitchen-print-flow-ok")
