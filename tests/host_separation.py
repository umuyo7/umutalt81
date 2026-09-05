import os
import re
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as directory:
    os.environ.update(
        DATABASE_URL="sqlite:///" + (Path(directory) / "host.db").as_posix(),
        APP_ENV="test", APP_PREFIX="", SESSION_SECRET="h" * 48, COOKIE_HTTPS_ONLY="true",
        CATERING_SSO_SECRET="s" * 48, CATERING_USERNAME="catering-host-test",
        CATERING_PASSWORD="Catering-Host-Test-123!", RESTAURANT_USERNAME="restaurant-host-test",
        RESTAURANT_PASSWORD="Restaurant-Host-Test-123!", CATERING_NATIVE_ENABLED="true",
        CATERING_BACKEND="native", POS_HOST="pos.bereketsofram.com",
        MANAGEMENT_HOST="yonetim.bereketsofram.com",
    )
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import engine

    def login(client, username, password):
        form = client.get("/login")
        token = re.search(r'const token = "([^"]+)"', form.text).group(1)
        return client.post("/login", data={"username": username, "password": password, "csrf_token": token}, follow_redirects=False)

    with TestClient(app, base_url="https://pos.bereketsofram.com") as client:
        assert login(client, "restaurant-host-test", "Restaurant-Host-Test-123!").status_code == 303
        assert client.get("/dashboard", follow_redirects=False).headers["location"] == "/yonetim"
        assert client.get("/restaurant").status_code == 404
        assert client.get("/catering-native/").status_code == 404

    with TestClient(app, base_url="https://yonetim.bereketsofram.com") as client:
        assert client.get("/pos/masalar", follow_redirects=False).headers["location"].startswith("https://pos.bereketsofram.com/")
        assert login(client, "catering-host-test", "Catering-Host-Test-123!").status_code == 303
        assert client.get("/dashboard", follow_redirects=False).headers["location"] == "/catering-native/"

    engine.dispose()

print("host-separation-ok")
