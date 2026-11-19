"""Copy a local SQLite snapshot into an empty, migrated PostgreSQL database.

Run as a one-off container command, before starting the application. The source
is read-only, all application rows are copied in one target transaction, and a
nonempty target is refused. Alembic owns the target schema/version separately.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, func, select, text

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base


def comparable(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    if not args.source.is_file():
        raise SystemExit("Source SQLite snapshot does not exist")
    source = create_engine(f"sqlite:///file:{args.source.resolve()}?mode=ro&uri=true")
    target = create_engine(settings.DATABASE_URL)
    if target.dialect.name != "postgresql":
        raise SystemExit("Target must be PostgreSQL")
    counts = {}
    with source.connect() as src, target.begin() as dst:
        tables = Base.metadata.sorted_tables
        for table in tables:
            if dst.scalar(select(func.count()).select_from(table)):
                raise SystemExit(f"Target table {table.name} is not empty; nothing imported")
        for table in tables:
            rows = [dict(row) for row in src.execute(select(table)).mappings()]
            if rows:
                dst.execute(table.insert(), rows)
            counts[table.name] = len(rows)
            # Validate all values, including hashes, identities, assignments,
            # ticket history and original SLA timestamps, before committing.
            columns = [column.name for column in table.primary_key]
            key = lambda row: tuple(row[column] for column in columns)
            copied = {key(row): row for row in dst.execute(select(table)).mappings()}
            assert len(copied) == len(rows), table.name
            for row in rows:
                assert all(comparable(value) == comparable(copied[key(row)][column])
                           for column, value in row.items()), table.name
            if "id" in table.c and rows:
                seq = dst.scalar(text("SELECT pg_get_serial_sequence(:table, 'id')"), {"table": table.name})
                if seq:
                    dst.execute(text("SELECT setval(:sequence, :next_id, false)"),
                                {"sequence": seq, "next_id": max(row["id"] for row in rows) + 1})
    print(json.dumps({"imported_and_verified": counts}))


if __name__ == "__main__":
    main()
