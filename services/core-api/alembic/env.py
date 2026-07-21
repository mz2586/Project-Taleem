"""Alembic environment for the curriculum_studio schema.

The URL comes from ``CS_DATABASE_URL`` (never hard-coded). ``target_metadata`` is the ORM metadata,
so ``--autogenerate`` can assist future migrations — but Postgres-specific objects (tsvector column,
triggers, partitioning, RLS, partial indexes) are hand-authored, because autogenerate does not see
them (DATABASE_ARCHITECTURE.md §20).
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from taleem_core.contexts.curriculum_studio.adapters.persistence.base import SCHEMA, Base

config = context.config

_url = os.environ.get("CS_DATABASE_URL")
if _url:
    config.set_main_option("sqlalchemy.url", _url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        version_table_schema=None,
        include_schemas=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema=None,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
