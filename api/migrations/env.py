from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.models import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
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
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.exec_driver_sql("PRAGMA synchronous=NORMAL")
            # SQLAlchemy starts an implicit transaction for these PRAGMAs.
            # Finish it before Alembic opens the transaction it owns below.
            connection.commit()
        # SQLite DDL is transactional when it is executed through SQLAlchemy.
        # Explicitly tell Alembic to manage that transaction so additive
        # migrations are committed before this connection closes.
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transactional_ddl=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()
        # Alembic's SQLite implementation can leave the SQLAlchemy-owned
        # transaction open after a migration. Commit it explicitly so the
        # revision marker and additive schema changes survive connection close.
        if connection.in_transaction():
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
