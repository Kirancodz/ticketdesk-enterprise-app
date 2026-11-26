from logging.config import fileConfig
from sqlalchemy import create_engine, pool, text
from sqlalchemy.exc import SQLAlchemyError
from alembic import context
from alembic.util import CommandError
from app.core.config import settings
from app.core.database import Base
import app.models  # noqa: F401 - Ensure all models are imported

config = context.config
if config.config_file_name is not None and config.cmd_opts is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        settings.DATABASE_URL,
        hide_parameters=True,
        poolclass=pool.NullPool,
    )

    try:
        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                if connection.dialect.name == "postgresql":
                    # Serialize Alembic commands across deployment processes.
                    connection.execute(text("SELECT pg_advisory_xact_lock(6073475853914031)"))
                context.run_migrations()
    except SQLAlchemyError as exc:
        raise CommandError(
            f"Database migration operation failed ({type(exc).__name__}). "
            "Check database connectivity, privileges, and the target schema."
        ) from None
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
