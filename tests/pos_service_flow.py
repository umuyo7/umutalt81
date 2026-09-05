import tempfile
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import BusinessType, User
from app.permissions import seed_permissions
from app.pos_models import (
    AuditLog,
    Category,
    Check,
    CheckStatus,
    Payment,
    Product,
    RestaurantTable,
    Role,
    TableSection,
    UserRole,
)
from app.pos_services import (
    add_item,
    apply_discount,
    close_check,
    create_payment,
    open_service,
)
from app.pos_models import DiscountType, PaymentMethod
from app.security import hash_password


with tempfile.TemporaryDirectory() as directory:
    engine = create_engine(f"sqlite:///{(Path(directory) / 'pos.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            seed_permissions(db)
            roles = {role.code: role for role in db.scalars(select(Role)).all()}
            waiter = User(name="Garson", username="waiter", password_hash=hash_password("Waiter-Test-123!"), business_type=BusinessType.RESTAURANT)
            cashier = User(name="Kasiyer", username="cashier", password_hash=hash_password("Cashier-Test-123!"), business_type=BusinessType.RESTAURANT)
            manager = User(name="Müdür", username="manager", password_hash=hash_password("Manager-Test-123!"), business_type=BusinessType.RESTAURANT)
            db.add_all([waiter, cashier, manager]); db.flush()
            db.add_all([
                UserRole(user_id=waiter.id, role_id=roles["waiter"].id),
                UserRole(user_id=cashier.id, role_id=roles["cashier"].id),
                UserRole(user_id=manager.id, role_id=roles["manager"].id),
            ])
            section = TableSection(name="İç Salon")
            category = Category(name="Ana Yemekler")
            db.add_all([section, category]); db.flush()
            table = RestaurantTable(section_id=section.id, code="1", display_name="Masa 1", capacity=4)
            product = Product(category_id=category.id, name="Test Ürünü", price=Decimal("100.00"))
            db.add_all([table, product]); db.commit()

            service, check = open_service(db, waiter.id, table.id, 4)
            db.commit()
            add_item(db, waiter.id, check.id, product.id, Decimal("2"))
            db.commit()
            apply_discount(db, manager.id, check.id, DiscountType.PERCENTAGE, Decimal("10"), "Test indirimi")
            db.commit()
            db.refresh(check)
            assert check.subtotal == Decimal("200.00")
            assert check.discount_total == Decimal("20.00")
            assert check.final_total == Decimal("180.00")

            # CHECK_REQUESTED yapılmadan kasiyer ödeme alabilir.
            first, replayed, notice = create_payment(db, cashier.id, check.id, PaymentMethod.CASH, Decimal("40"), "pay-1")
            db.commit()
            assert not replayed and notice
            replay, replayed, _ = create_payment(db, cashier.id, check.id, PaymentMethod.CASH, Decimal("40"), "pay-1")
            db.commit()
            assert replayed and replay.id == first.id
            assert db.scalar(select(func.count(Payment.id))) == 1

            create_payment(db, cashier.id, check.id, PaymentMethod.CREDIT_CARD, Decimal("140"), "pay-2")
            db.commit()
            db.refresh(check)
            assert check.balance_due == Decimal("0.00") and check.status == CheckStatus.PAID
            close_check(db, cashier.id, check.id)
            db.commit()
            assert check.status == CheckStatus.CLOSED
            assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "PAYMENT_CREATE_WITHOUT_CHECK_REQUEST")) == 2

            try:
                create_payment(db, waiter.id, check.id, PaymentMethod.CASH, Decimal("1"), "waiter-pay")
            except PermissionError:
                db.rollback()
            else:
                raise AssertionError("Garson ödeme alamamalıydı")
    finally:
        engine.dispose()

print("pos-service-flow-ok")
