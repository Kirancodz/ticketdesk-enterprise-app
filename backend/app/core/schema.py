from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection


class SchemaNotCurrent(RuntimeError):
    """The database revision does not match the application release."""


@lru_cache(maxsize=1)
def migration_heads() -> frozenset[str]:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def require_current_schema(connection: Connection) -> None:
    expected = migration_heads()
    current = frozenset(MigrationContext.configure(connection).get_current_heads())
    if not expected or current != expected:
        raise SchemaNotCurrent("Database schema is not at Alembic head. Run the migration operation first.")
