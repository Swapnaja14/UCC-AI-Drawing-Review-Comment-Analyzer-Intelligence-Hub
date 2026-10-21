"""
alembic/env.py
Alembic migration environment for UCC AI Drawing Review Comment Analyzer.

Supports both SQLite (default) and PostgreSQL backends.
Connection URL is resolved from (in priority order):
  1. UCC_DATABASE_URL environment variable
  2. DATABASE_URL environment variable
  3. config.yaml → database.url (postgresql only)
  4. SQLite file at data/ucc_database.db

For PostgreSQL, use timezone=True on DateTime columns so timestamps are
stored as TIMESTAMP WITH TIME ZONE (via the autogenerate render hook below).
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Make project packages importable when alembic is run from the project root.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------------------------
config = context.config

# Set up loggers from alembic.ini (only if a config file is present)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import project models so autogenerate can diff against the live schema
# ---------------------------------------------------------------------------
from src.infrastructure.storage.models import Base  # noqa: E402

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Resolve the effective database URL (mirrors DatabaseEngine logic)
# ---------------------------------------------------------------------------

def _get_db_url() -> str:
    """Return the database URL for migrations, honouring env-var overrides."""
    # Check if a non-placeholder URL was set in Alembic Config (e.g. from tests or CLI -x)
    cfg_url = config.get_main_option("sqlalchemy.url")
    if cfg_url and not cfg_url.startswith("driver://") and not cfg_url.strip() == "":
        return cfg_url
    env_url = os.environ.get("UCC_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    # Try config.yaml backend / url
    try:
        from src.config.app_config import AppConfig, DEFAULT_CONFIG_PATH
        cfg = AppConfig.load_from_yaml(DEFAULT_CONFIG_PATH)
        return cfg.database.get_url()
    except Exception:
        pass
    # Last-resort: default SQLite path
    db_path = _PROJECT_ROOT / "data" / "ucc_database.db"
    return f"sqlite:///{db_path.as_posix()}"


def _is_postgresql(url: str) -> bool:
    return url.startswith("postgresql") or url.startswith("postgres")


# ---------------------------------------------------------------------------
# compare_type helper: detect when column types change between runs
# ---------------------------------------------------------------------------

def _include_schemas(name, type_, parent_names, reflected, compare_to):
    """Exclude the legacy schema_migrations table from Alembic's scope."""
    if type_ == "table" and name == "schema_migrations":
        return False
    return True


# ---------------------------------------------------------------------------
# Offline migrations (generate SQL without a live DB connection)
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL dump to stdout/file)."""
    url = _get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_schemas,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations (live connection)
# ---------------------------------------------------------------------------

def run_migrations_online() -> None:
    """Run migrations in 'online' mode (against a live database)."""
    url = _get_db_url()
    is_pg = _is_postgresql(url)

    # Build engine config dict for engine_from_config
    cfg_section = config.get_section(config.config_ini_section, {})
    cfg_section["sqlalchemy.url"] = url

    pool_class = pool.NullPool if is_pg else pool.StaticPool

    connectable = engine_from_config(
        cfg_section,
        prefix="sqlalchemy.",
        poolclass=pool_class,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_schemas,
            compare_type=True,
            # For SQLite: render AS without COMMIT (autocommit handled by context)
            render_as_batch=not is_pg,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
