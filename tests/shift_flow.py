import tempfile
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import BusinessType, User
from app.permissions import permission_decision, seed_permissions
from app.pos_models import Category, PaymentMethod, Product, RestaurantTable, Role, TableSection, UserRole
from app.pos_services import PosError, add_item, close_check, close_shift, create_payment, open_service, open_shift, shift_summary


with tempfile.TemporaryDirectory() as directory:
    engine = create_engine(f"sqlite:///{(Path(directory) / 'shift.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            seed_permissions(db)
            roles = {row.code: row for row in db.scalars(select(Role)).all()}
            waiter = User(name="Garson", username="shift-waiter", password_hash="test", business_type=BusinessType.RESTAURANT)
            cashier = User(name="Kasiyer", username="shift-cashier", password_hash="test", business_type=BusinessType.RESTAURANT)
            section, category = TableSection(name="Vardiya Salon"), Category(name="Vardiya Menü")
            db.add_all([waiter, cashier, section, category]); db.flush()
            db.add_all([UserRole(user_id=waiter.id, role_id=roles["waiter"].id), UserRole(user_id=cashier.id, role_id=roles["cashier"].id)])
            table = RestaurantTable(section_id=section.id, code="V1", display_name="Masa V1", capacity=4)
            product = Product(category_id=category.id, name="Menü", price=Decimal("100.00"))
            db.add_all([table, product]); db.commit()
            assert permission_decision(db, cashier.id, "shift.open").allowed
            assert not permission_decision(db, waiter.id, "shift.open").allowed
            assert not permission_decision(db, waiter.id, "shift.close").allowed

            shift = open_shift(db, cashier.id, Decimal("500")); db.commit()
            _, check = open_service(db, waiter.id, table.id, 2)
            add_item(db, waiter.id, check.id, product.id, Decimal("2")); db.commit()
            cash, _, _ = create_payment(db, cashier.id, check.id, PaymentMethod.CASH, Decimal("120"), "shift-cash")
            card, _, _ = create_payment(db, cashier.id, check.id, PaymentMethod.CREDIT_CARD, Decimal("80"), "shift-card")
            db.commit()
            assert cash.shift_id == shift.id == card.shift_id
            summary = shift_summary(db, shift)
            assert summary["totals"][PaymentMethod.CASH] == Decimal("120.00")
            assert summary["totals"][PaymentMethod.CREDIT_CARD] == Decimal("80.00")
            assert summary["expected_cash_amount"] == Decimal("620.00")
            try:
                close_shift(db, cashier.id, Decimal("615"))
            except PosError as exc:
                db.rollback(); assert exc.code == "OPEN_CHECKS_EXIST"
            else:
                raise AssertionError("Açık adisyon varken vardiya kapanmamalıydı")
            close_check(db, cashier.id, check.id); db.commit()
            shift, summary = close_shift(db, cashier.id, Decimal("615"), "Beş lira eksik"); db.commit()
            assert shift.expected_cash_amount == Decimal("620.00")
            assert shift.cash_difference == Decimal("-5.00")
            assert summary["totals"][PaymentMethod.MEAL_CARD] == Decimal("0.00")
    finally:
        engine.dispose()

print("shift-flow-ok")
