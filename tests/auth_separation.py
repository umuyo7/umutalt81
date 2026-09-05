import os
import re

os.environ["DATABASE_URL"] = "sqlite:///./smoke.db"
os.environ["APP_ENV"] = "test"
os.environ["SESSION_SECRET"] = "test-session-secret-that-is-long-enough-123456"
os.environ["COOKIE_HTTPS_ONLY"] = "true"
os.environ["APP_PREFIX"] = "/giris/xyz"
os.environ["CATERING_USERNAME"] = "catering-test"
os.environ["CATERING_PASSWORD"] = "Catering-Test-123!"
os.environ["RESTAURANT_USERNAME"] = "restaurant-test"
os.environ["RESTAURANT_PASSWORD"] = "Restaurant-Test-123!"
os.environ["CATERING_SSO_SECRET"] = "catering-sso-test-secret-that-is-long-enough-123456"

from fastapi.testclient import TestClient

from app.main import app


with TestClient(app, base_url="https://testserver") as client:
    assert client.get("/service-worker.js").headers["service-worker-allowed"] == "/giris/xyz/"
    assert client.get("/register", follow_redirects=False).status_code == 303
    assert client.get("/login").headers["cache-control"] == "no-store, private"

    def csrf(path: str) -> str:
        response = client.get(path)
        assert '/giris/xyz/static/app.css' in response.text
        return re.search(r'const token = "([^"]+)"', response.text).group(1)

    response = client.post("/login", data={"username": "catering-test", "password": "Catering-Test-123!", "csrf_token": csrf("/login")}, follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/login", follow_redirects=False).headers["location"] == "/giris/xyz/dashboard"
    assert client.get("/dashboard", follow_redirects=False).headers["location"] == "/giris/xyz/legacy-catering-entry"
    assert client.get("/legacy-catering-entry", follow_redirects=False).headers["location"].startswith("/giris/xyz/catering/sso.php?")
    assert client.get("/catering/customers").status_code == 200
    assert client.get("/catering/daily").status_code == 200
    assert client.get("/catering/customers/1").status_code == 200
    assert client.get("/catering/customers/1/statement/summary.pdf").status_code == 200
    assert client.get("/restaurant", follow_redirects=False).headers["location"] == "/giris/xyz/dashboard"
    assert client.post("/catering/customers", data={"company_name": "CSRF", "csrf_token": "yanlis"}).status_code == 403

    client.post("/logout", data={"csrf_token": csrf("/catering/customers")})
    response = client.post("/login", data={"username": "restaurant-test", "password": "Restaurant-Test-123!", "csrf_token": csrf("/login")}, follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/restaurant").status_code == 200
    assert client.get("/restaurant/employees").status_code == 200
    assert client.get("/restaurant/reports").status_code == 200
    assert client.get("/catering/customers", follow_redirects=False).headers["location"] == "/giris/xyz/dashboard"

print("auth-separation-ok")
