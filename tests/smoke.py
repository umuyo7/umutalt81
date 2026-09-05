import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./smoke.db"
os.environ["CATERING_USERNAME"] = "catering-test"
os.environ["RESTAURANT_USERNAME"] = "restaurant-test"

from app.db import Base, SessionLocal, engine
from app.import_legacy import import_file
from app.models import BusinessType, Customer, Employee, Expense, LegacyImport, User
from app.security import _hash_password_scrypt, hash_password, password_needs_rehash, verify_password

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    db.add_all([
        User(name="Catering", username="catering-test", password_hash=hash_password("Catering-Test-123!"), business_type=BusinessType.CATERING),
        User(name="Restoran", username="restaurant-test", password_hash=hash_password("Restaurant-Test-123!"), business_type=BusinessType.RESTAURANT),
    ])
    db.commit()

counts = import_file(Path("tests/legacy_fixture.json"))
assert counts["musteriler"] == 1
assert counts["gunluk_giderler"] == 1

with SessionLocal() as db:
    catering = db.query(User).filter(User.username == "catering-test").one()
    restaurant = db.query(User).filter(User.username == "restaurant-test").one()
    assert db.query(Customer).filter(Customer.user_id == catering.id).count() == 1
    assert db.query(Customer).filter(Customer.user_id == restaurant.id).count() == 0
    assert db.query(Expense).filter(Expense.user_id == restaurant.id).count() == 1
    assert db.query(Employee).filter(Employee.user_id == restaurant.id).count() == 1
    assert db.query(LegacyImport).count() == 1
    assert verify_password("Catering-Test-123!", catering.password_hash)
    legacy = _hash_password_scrypt("Legacy-Test-123!")
    assert verify_password("Legacy-Test-123!", legacy)
    assert password_needs_rehash(legacy)
    assert not password_needs_rehash(hash_password("Modern-Test-123!"))

try:
    import_file(Path("tests/legacy_fixture.json"))
except RuntimeError as exc:
    assert "daha önce" in str(exc)
else:
    raise AssertionError("Aynı aktarım ikinci kez kabul edilmemeliydi")

print("smoke-test-ok")
