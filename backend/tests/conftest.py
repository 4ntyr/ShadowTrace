import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp()
os.environ["ST_DATABASE_URL"] = os.environ.get("ST_TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["ST_SECRET_KEY"] = "test-secret-" + "x" * 40
os.environ.pop("ST_OTX_API_KEY", None)
os.environ.pop("ST_ACLED_USERNAME", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, get_engine, reset_engine  # noqa: E402
from app.ingest.runner import bootstrap  # noqa: E402
from app.main import app  # noqa: E402

HEADERS = {"X-Requested-With": "shadowtrace"}


@pytest.fixture(scope="session", autouse=True)
def database():
    get_settings.cache_clear()
    reset_engine()
    from app import models  # noqa: F401
    from app.db import init_db

    Base.metadata.drop_all(get_engine())
    with get_engine().begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    init_db()  # exercises the real migrations
    db = SessionLocal()
    bootstrap(db)
    db.close()
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def client():
    from app.security import auth_limiter

    auth_limiter.hits.clear()  # all test clients share one "IP"
    with TestClient(app) as c:
        c.headers.update(HEADERS)
        yield c


@pytest.fixture
def user_client(client):
    import uuid

    email = f"analyst-{uuid.uuid4().hex[:8]}@example.org"
    r = client.post("/api/auth/register", json={"email": email, "password": "correct horse battery", "display_name": "Analyst"})
    assert r.status_code == 201, r.text
    return client
