"""Alembic environment. The database URL comes from app settings (ST_DATABASE_URL).

The app runs `upgrade head` on startup (app.db.init_db), passing its own connection via
config.attributes["connection"]. From the CLI:  alembic upgrade head / alembic revision --autogenerate -m "..."
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401  (register tables)
from app.config import get_settings
from app.db import Base

config = context.config
target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    conn = config.attributes.get("connection")
    if conn is not None:
        _configure(conn)
        return
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    engine = engine_from_config(
        {"sqlalchemy.url": get_settings().database_url}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with engine.connect() as connection:
        _configure(connection)
        connection.commit()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
