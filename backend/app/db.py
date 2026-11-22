from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        kwargs = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs = {"connect_args": {"check_same_thread": False}}
        _engine = create_engine(url, **kwargs)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def SessionLocal() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def reset_engine() -> None:
    """Used by tests after changing ST_DATABASE_URL."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Bring the schema to the latest Alembic revision. Safe to call from several processes."""
    from alembic import command
    from alembic.config import Config

    from . import models  # noqa: F401  (register tables)

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    engine = get_engine()
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            # API and worker start together; serialise migrations with an advisory lock.
            conn.execute(text("SELECT pg_advisory_xact_lock(7426001)"))
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        if "groups" in tables and "alembic_version" not in tables:
            # Database created by a pre-migration build (create_all): adopt it as the initial revision.
            command.stamp(cfg, "0001")
        command.upgrade(cfg, "head")
