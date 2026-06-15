"""Alembic migration environment for PF Coach.

Run from the ``backend/`` directory (where ``alembic.ini`` lives) so the local modules
import cleanly. The database URL comes from ``config.settings`` — not ``alembic.ini`` — so
the same env config works locally and on Railway.
"""

from logging.config import fileConfig

from alembic import context

from config import settings
from database import Base, engine

# Import models so every table is registered on Base.metadata for autogenerate.
import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Make the resolved URL visible to Alembic logging/tools.
config.set_main_option("sqlalchemy.url", settings.normalized_database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection (`alembic upgrade --sql`)."""
    context.configure(
        url=settings.normalized_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
