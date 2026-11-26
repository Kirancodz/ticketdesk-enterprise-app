"""Provision the first administrator from a controlled deployment terminal."""

import argparse
import sys
import warnings
from getpass import GetPassWarning, getpass

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import AuditLog, Role, RoleName, User
from app.services.audit_service import record_audit_log


BOOTSTRAP_ACTION = "INITIAL_ADMIN_PROVISIONED"


class BootstrapError(Exception):
    """An operator-facing error that contains no supplied input."""


def provision_initial_admin(db: Session, *, email: str, full_name: str, password: str) -> None:
    try:
        email = validate_email(email.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise BootstrapError("Provide a valid administrator email address.") from None
    full_name = " ".join(full_name.split())
    if len(email) > 255 or not 2 <= len(full_name) <= 150:
        raise BootstrapError("The administrator identity exceeds the allowed limits or is incomplete.")
    if len(password) < 16 or len(password.encode("utf-8")) > 72 or not password.strip():
        raise BootstrapError("Use a unique password of at least 16 characters and no more than 72 UTF-8 bytes.")
    password_hash = get_password_hash(password)

    with db.begin():
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            # Serialize the first-admin check and insert, even with no users yet.
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            db.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
        elif dialect == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        else:
            raise BootstrapError("Bootstrap supports PostgreSQL and SQLite.")

        admin_name = RoleName.ADMIN.value
        roles = (
            db.query(Role)
            .filter(func.lower(Role.name) == admin_name)
            .with_for_update()
            .all()
        )
        if len(roles) != 1 or roles[0].name != admin_name:
            raise BootstrapError("The administrator role is missing, invalid, or ambiguous.")
        role = roles[0]

        if db.query(User.id).filter(func.lower(User.email) == email).first():
            raise BootstrapError("The supplied identity already belongs to an account. No account was changed.")
        if (
            db.query(User.id).filter(User.role_id == role.id).first()
            or db.query(AuditLog.id).filter_by(action=BOOTSTRAP_ACTION).first()
        ):
            raise BootstrapError("An administrator already exists or bootstrap was previously completed.")

        admin = User(
            email=email,
            full_name=full_name,
            role_id=role.id,
            hashed_password=password_hash,
            is_active=True,
        )
        db.add(admin)
        db.flush()
        record_audit_log(db, None, BOOTSTRAP_ACTION, "user", entity_id=admin.id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    args, unknown_args = parser.parse_known_args(argv)
    if unknown_args:
        parser.error("Unrecognized arguments.")

    try:
        with warnings.catch_warnings():
            # Abort if getpass would fall back to reading visible input.
            warnings.simplefilter("error", GetPassWarning)
            password = getpass("Administrator password: ")
            confirmation = getpass("Confirm administrator password: ")
        if password != confirmation:
            raise BootstrapError("The passwords did not match.")
        with SessionLocal() as db:
            provision_initial_admin(db, email=args.email, full_name=args.full_name, password=password)
    except (GetPassWarning, EOFError, KeyboardInterrupt):
        print("Bootstrap cancelled. Use a terminal with hidden password input.", file=sys.stderr)
        return 1
    except BootstrapError as exc:
        print(f"Bootstrap refused: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Bootstrap failed. Check the database schema, permissions, and concurrent activity.", file=sys.stderr)
        return 1

    print("Initial administrator created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
