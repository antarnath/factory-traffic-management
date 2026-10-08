"""Alembic environment configuration.

Reads the DB URL from `app.config.settings` (which loads `.env`) and the
metadata from `app.db.Base`. Every model is registered by importing
`app.models` so autogenerate can find them.
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure `app.*` imports work when Alembic is invoked from `backend/`.
os.environ.setdefault("PYTHONPATH", ".")

from app.config import settings  # noqa: E402
from app.db import Base          # noqa: E402

# IMPORTANT: import models so they are registered on Base.metadata.
import app.models  # noqa: F401, E402

config = context.config

# Override the URL from .ini with the one from app settings.
config.set_main_option("sqlalchemy.url", settings.db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without an active DB connection (emits SQL)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
