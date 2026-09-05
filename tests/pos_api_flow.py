import os
import re
import tempfile
from pathlib import Path


with tempfile.TemporaryDirectory() as directory:
    database = Path(directory) / "api.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    os.environ["APP_ENV"] = "test"
    os.environ["SESSION_SECRET"] = "test-session-secret-that-is-long-enough-123456"
    os.environ["COOKIE_HTTPS_ONLY"] = "true"
    os.environ["APP_PREFIX"] = ""
    os.environ["CATERING_USERNAME"] = "catering-api"
    os.environ["CATERING_PASSWORD"] = "Catering-Api-123!"
    os.environ["RESTAURANT_USERNAME"] = "restaurant-api"
    os.environ["RESTAURANT_PASSWORD"] = "Restaurant-Api-123!"
    os.environ["CATERING_SSO_SECRET"] = "catering-sso-test-secret-that-is-long-enough-123456"

    from fastapi.testclient import TestClient
    from app.db import SessionLocal, engine
    from app.main import app
    from app.pos_models import AuditLog, LoginSession

    with TestClient(app, base_url="https://testserver") as client:
        login_page = client.get("/login")
        worker = client.get("/service-worker.js")
        assert worker.status_code == 200 and worker.headers["service-worker-allowed"] == "/"
        csrf = re.search(r'const token = "([^"]+)"', login_page.text).group(1)
        response = client.post("/login", data={"username": "restaurant-api", "password": "Restaurant-Api-123!", "csrf_token": csrf}, follow_redirects=False)
        assert response.status_code == 303
        tables_page = client.get("/pos/masalar")
        assert tables_page.status_code == 200 and "Masalar" in tables_page.text
        csrf = re.search(r'const token = "([^"]+)"', tables_page.text).group(1)
        headers = {"X-CSRF-Token": csrf}

        section = client.post("/api/v1/admin/sections", json={"name": "İç Salon"}, headers=headers).json()["data"]
        table = client.post("/api/v1/admin/tables", json={"section_id": section["id"], "code": "1", "display_name": "Masa 1", "capacity": 4}, headers=headers).json()["data"]
        category = client.post("/api/v1/admin/categories", json={"name": "Yemekler"}, headers=headers).json()["data"]
        product = client.post("/api/v1/admin/products", json={"category_id": category["id"], "name": "Köfte", "price": "250.00"}, headers=headers).json()["data"]

        opened = client.post("/api/v1/services", json={"table_id": table["id"], "guest_count": 3}, headers=headers).json()["data"]
        check_id = opened["check_id"]
        added = client.post(f"/api/v1/checks/{check_id}/items", json={"product_id": product["id"], "quantity": "2"}, headers=headers)
        assert added.status_code == 200
        kitchen = client.post(f"/pos/masa/{table['id']}/mutfaga-gonder", data={"csrf_token": csrf})
        assert kitchen.status_code == 200 and "MUTFAK" in kitchen.text and "Köfte" in kitchen.text
        assert "250,00" not in kitchen.text and "500,00" not in kitchen.text
        shift = client.post("/api/v1/shifts/open", json={"opening_cash_amount": "100.00"}, headers=headers)
        assert shift.status_code == 200

        payment_headers = {**headers, "Idempotency-Key": "api-payment-1"}
        paid = client.post("/api/v1/payments", json={"check_id": check_id, "payment_method": "CREDIT_CARD", "amount": "500.00"}, headers=payment_headers)
        assert paid.status_code == 200
        assert "hesap talebi oluşturulmadan" in paid.json()["data"]["notice"]
        replay = client.post("/api/v1/payments", json={"check_id": check_id, "payment_method": "CREDIT_CARD", "amount": "500.00"}, headers=payment_headers)
        assert replay.json()["data"]["replayed"] is True

        detail = client.get(f"/api/v1/checks/{check_id}").json()["data"]
        assert detail["totals"]["balance"] == "0.00"
        closed = client.post(f"/api/v1/checks/{check_id}/close", json={}, headers=headers)
        assert closed.status_code == 200 and closed.json()["data"]["status"] == "CLOSED"
        receipt = client.get(f"/kasa/fis/{check_id}")
        assert receipt.status_code == 200 and "KDV (dahil)" in receipt.text and "500,00" in receipt.text
        shift_closed = client.post("/api/v1/shifts/close", json={"closing_cash_amount": "100.00", "note": "API test kapanışı"}, headers=headers)
        assert shift_closed.status_code == 200 and shift_closed.json()["data"]["cash_difference"] == "0.00"
        assert client.get("/yonetim/vardiyalar").status_code == 200
        assert client.get("/kasa").status_code == 200
        assert client.get("/yonetim").status_code == 200
        reports_page = client.get("/yonetim/raporlar")
        assert reports_page.status_code == 200 and "Garson performansı" in reports_page.text
        datetime_module = __import__("datetime")
        today = datetime_module.datetime.now(datetime_module.UTC).date().isoformat()
        operations = client.get(f"/api/v1/reports/operations?date_from={today}&date_to={today}")
        assert operations.status_code == 200
        assert operations.json()["data"]["summary"]["net"] == "500.00", operations.text
        operations_csv = client.get(f"/api/v1/reports/operations.csv?date_from={today}&date_to={today}")
        assert operations_csv.status_code == 200 and "Garson performansı" in operations_csv.text
        assert client.get("/yonetim/tanimlar").status_code == 200
        assert client.get(f"/yonetim/adisyon/{check_id}").status_code == 200
        exported = client.get("/api/v1/reports/daily.csv")
        assert exported.status_code == 200 and "text/csv" in exported.headers["content-type"]
        assert exported.content.startswith(b"\xef\xbb\xbf")
        assert client.get("/dashboard").headers["x-content-type-options"] == "nosniff"
        created_user = client.post("/api/v1/admin/users", json={"name": "Test Garson", "username": "test-garson", "password": "Garson-Test-123!", "role_code": "waiter"}, headers=headers).json()["data"]
        updated_user = client.patch(f"/api/v1/admin/users/{created_user['id']}", json={"name": "Test Şef", "role_code": "head_waiter", "is_active": False, "reason": "Test güncellemesi"}, headers=headers)
        assert updated_user.status_code == 200 and updated_user.json()["data"]["active"] is False
        updated_product = client.patch(f"/api/v1/admin/products/{product['id']}", json={"category_id": category["id"], "name": "Köfte Güncel", "price": "275.00", "is_active": False, "reason": "Menü güncellemesi"}, headers=headers)
        assert updated_product.status_code == 200 and updated_product.json()["data"]["price"] == "275.00"
        updated_table = client.patch(f"/api/v1/admin/tables/{table['id']}", json={"display_name": "Masa 1A", "capacity": 6, "is_active": False, "reason": "Salon düzeni"}, headers=headers)
        assert updated_table.status_code == 200 and updated_table.json()["data"]["active"] is False
        updated_category = client.patch(f"/api/v1/admin/categories/{category['id']}", json={"name": "Yemekler Arşiv", "is_active": False, "reason": "Menü arşivi"}, headers=headers)
        assert updated_category.status_code == 200 and updated_category.json()["data"]["active"] is False
        updated_section = client.patch(f"/api/v1/admin/sections/{section['id']}", json={"name": "İç Salon Arşiv", "is_active": False, "reason": "Salon arşivi"}, headers=headers)
        assert updated_section.status_code == 200 and updated_section.json()["data"]["active"] is False
        roles_payload = client.get("/api/v1/admin/roles").json()["data"]
        waiter_role = next(row for row in roles_payload["roles"] if row["code"] == "waiter")
        role_update = client.put(f"/api/v1/admin/roles/{waiter_role['id']}/permissions", json={"permission_codes": ["service.open"], "discount_max_percent": "0", "reason": "Test matrisi"}, headers=headers)
        assert role_update.status_code == 200 and role_update.json()["data"]["allowed"] == ["service.open"]
        with SessionLocal() as db:
            session_id = db.query(LoginSession.id).filter(LoginSession.revoked_at.is_(None)).scalar()
            assert session_id
        logged_out = client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)
        assert logged_out.status_code == 303
        with SessionLocal() as db:
            assert db.get(LoginSession, session_id).revoked_at is not None
            assert db.query(AuditLog).filter(AuditLog.action == "LOGIN").count() == 1
            assert db.query(AuditLog).filter(AuditLog.action == "LOGOUT").count() == 1
            payment_audit = db.query(AuditLog).filter(AuditLog.action == "PAYMENT_CREATE_WITHOUT_CHECK_REQUEST").first()
            assert payment_audit.request_id and payment_audit.session_id == session_id, (payment_audit.request_id, payment_audit.session_id, session_id)
        assert client.get("/api/v1/me").status_code == 401

    engine.dispose()

print("pos-api-flow-ok")
