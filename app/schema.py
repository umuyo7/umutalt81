import os
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine


PROJECT_DIR = Path(__file__).resolve().parent.parent


def assert_schema_current(engine: Engine) -> None:
    config = Config(str(PROJECT_DIR / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    expected_revision = scripts.get_current_head()
    with engine.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()
    if current_revision != expected_revision:
        raise RuntimeError(
            "Veritabanı şeması güncel değil. "
            f"Mevcut revision: {current_revision or 'yok'}, beklenen: {expected_revision}. "
            "Uygulamayı başlatmadan önce `alembic upgrade head` çalıştırın."
        )


def should_auto_create_test_schema() -> bool:
    return os.getenv("APP_ENV", "production").strip().lower() == "test"
