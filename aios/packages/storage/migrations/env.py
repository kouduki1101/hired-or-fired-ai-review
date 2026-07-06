"""Alembic 実行環境。

- target_metadata は aios_storage.models.Base(単一の真実源、NFR-OP-05)
- 接続URLは AIOS_ALEMBIC_URL(同期ドライバ)。asyncドライバ表記が来た場合は
  同期表記へ変換する(+aiosqlite / +asyncpg を除去)
"""

from __future__ import annotations

import os

from aios_storage.models import Base
from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    url = os.environ.get("AIOS_ALEMBIC_URL") or os.environ.get("AIOS_DATABASE_URL")
    if not url:
        raise RuntimeError("set AIOS_ALEMBIC_URL (sync driver URL) to run migrations")
    return url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
