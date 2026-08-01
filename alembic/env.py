import os

from sqlalchemy import engine_from_config, pool

from alembic import context
from backend.storage import models  # noqa: F401
from backend.storage.database import Base, normalize_database_url

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    override = config.attributes.get("database_url")
    if isinstance(override, str) and override:
        return normalize_database_url(override)

    configured = os.getenv("CAREPATH_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    return normalize_database_url(configured)


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
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
