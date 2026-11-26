import os
import warnings
from concurrent.futures import ThreadPoolExecutor
from getpass import GetPassWarning
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app import bootstrap_admin, main
from app.bootstrap_admin import BOOTSTRAP_ACTION, BootstrapError, provision_initial_admin
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.schema import SchemaNotCurrent, migration_heads
from app.core.security import verify_password
from app.models import AuditLog, Department, KnowledgeArticle, Role, SLAPolicy, SupportTeam, SystemSetting, TicketCategory, User
from app.services.seed_service import initialize_reference_data


PASSWORD = "fixture-passphrase-5Cr9"


@pytest.fixture
def unmigrated_sessions(tmp_path):
    postgres_url = os.environ.get("TICKETDESK_BOOTSTRAP_TEST_POSTGRES_URL")
    if postgres_url:
        # Use a fresh, test-owned schema even when several tests share a server.
        schema = f"bootstrap_test_{uuid4().hex}"
        url = make_url(postgres_url).update_query_dict({"options": f"-c search_path={schema}"})
        engine = create_engine(url)
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'bootstrap.db'}")
    try:
        yield sessionmaker(bind=engine)
    finally:
        if postgres_url:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def migrate(monkeypatch, sessions, revision):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with monkeypatch.context() as patch:
        patch.setattr(settings, "DATABASE_URL", sessions.kw["bind"].url.render_as_string(hide_password=False))
        command.upgrade(config, revision)


@pytest.fixture
def sessions(monkeypatch, unmigrated_sessions):
    migrate(monkeypatch, unmigrated_sessions, "head")
    return unmigrated_sessions


@pytest.fixture
def ready_db(sessions):
    with sessions.begin() as db:
        assert initialize_reference_data(db)
    return sessions


def provision(sessions, email="owner@example.com", password=PASSWORD):
    with sessions() as db:
        provision_initial_admin(db, email=email, full_name="POC Administrator", password=password)


def start_app(monkeypatch, sessions, environment):
    monkeypatch.setattr(settings, "APP_ENV", environment)
    monkeypatch.setattr(main, "SessionLocal", sessions)
    monkeypatch.setattr(main, "engine", sessions.kw["bind"])

    def test_db():
        with sessions() as db:
            yield db

    monkeypatch.setitem(main.app.dependency_overrides, get_db, test_db)
    return TestClient(main.app)


def test_production_startup_seeds_reference_data_without_accounts(monkeypatch, sessions):
    for _ in range(2):
        with start_app(monkeypatch, sessions, "production") as client:
            assert client.get("/health").json()["status"] == "ok"
        with sessions() as db:
            assert db.query(User).count() == 0
            assert db.query(KnowledgeArticle).count() == 0
            assert db.query(Role).count() == 3
            assert db.query(TicketCategory).count() > 0


def test_production_startup_fills_missing_reference_data_without_overwriting(monkeypatch, sessions):
    with sessions.begin() as db:
        db.add(Role(name="admin", display_name="Existing Administrator"))
        db.add(SystemSetting(key="organization_name", value="Existing Organization"))
    for _ in range(2):
        with start_app(monkeypatch, sessions, "production") as client:
            assert client.get("/health").status_code == 200
    with sessions() as db:
        assert db.query(Role).filter_by(name="admin").one().display_name == "Existing Administrator"
        assert db.query(SystemSetting).filter_by(key="organization_name").one().value == "Existing Organization"
        assert db.query(Role).count() == 3
        assert db.query(Department).count() == 7
        assert db.query(SupportTeam).count() == 4
        assert db.query(TicketCategory).count() == 6
        assert db.query(SLAPolicy).count() == 4
        assert db.query(SystemSetting).count() == 7
        assert db.query(User).count() == 0
        assert db.query(KnowledgeArticle).count() == 0


def test_migrations_match_required_tables_and_constraints(sessions):
    with sessions() as db:
        assert frozenset(db.execute(text("SELECT version_num FROM alembic_version")).scalars()) == migration_heads()
        schema = inspect(db.connection())
        assert set(Base.metadata.tables) <= set(schema.get_table_names())
        assert schema.get_pk_constraint("sla_alert_deliveries")["constrained_columns"] == ["user_id", "ticket_id"]
        assert schema.get_pk_constraint("ticket_work_records")["constrained_columns"] == ["ticket_id", "user_id"]
        assert ("successor_ticket_id",) in {
            tuple(item["column_names"]) for item in schema.get_unique_constraints("ticket_transfer_links")
        }
        indexes = {item["name"]: item for item in schema.get_indexes("users")}
        assert indexes["ix_users_email"]["unique"]
        assert indexes["ix_users_session_identity"]["unique"]
        assert ("status", "priority") in {
            tuple(item["column_names"]) for item in schema.get_indexes("tickets")
        }
        assert {
            ("requester_id", "users", "RESTRICT"),
            ("assigned_agent_id", "users", "SET NULL"),
            ("category_id", "ticket_categories", "RESTRICT"),
        } <= {
            (item["constrained_columns"][0], item["referred_table"], item["options"].get("ondelete"))
            for item in schema.get_foreign_keys("tickets")
        }


@pytest.mark.parametrize("revision", [None, "0004_stable_account_sessions"])
def test_production_rejects_unmigrated_or_outdated_schema(monkeypatch, unmigrated_sessions, revision):
    if revision:
        migrate(monkeypatch, unmigrated_sessions, revision)
    before = inspect(unmigrated_sessions.kw["bind"]).get_table_names()
    with pytest.raises(SchemaNotCurrent, match="not at Alembic head"):
        with start_app(monkeypatch, unmigrated_sessions, "production"):
            pytest.fail("Startup should have failed")
    assert inspect(unmigrated_sessions.kw["bind"]).get_table_names() == before
    if revision:
        with unmigrated_sessions() as db:
            assert db.query(Role).count() == 0


def test_production_readiness_rejects_outdated_schema(monkeypatch, sessions):
    with start_app(monkeypatch, sessions, "production") as client:
        assert client.get("/health").json()["database"]["schema"] == "current"
        with sessions.begin() as db:
            db.execute(text("UPDATE alembic_version SET version_num = '0004_stable_account_sessions'"))
        for path in ("/health", "/api/v1/health"):
            response = client.get(path)
            assert response.status_code == 503
            assert response.json()["database"]["schema"] == "out_of_date"


def test_production_startup_and_readiness_reject_database_failure(monkeypatch, sessions, caplog):
    unavailable = False
    secret = "simulated-driver-secret"
    engine = sessions.kw["bind"]

    def reject_connection(*_args):
        if unavailable:
            raise OperationalError(None, None, RuntimeError(secret))

    event.listen(engine, "checkout", reject_connection)
    try:
        with start_app(monkeypatch, sessions, "production") as client:
            unavailable = True
            response = client.get("/health")
            assert response.status_code == 503
            assert response.json()["database"]["status"] == "unhealthy"
            assert secret not in response.text

        with pytest.raises(RuntimeError, match="Check connectivity") as failure:
            with start_app(monkeypatch, sessions, "production"):
                pytest.fail("Startup should have failed")
        assert secret not in str(failure.value)
        assert secret not in caplog.text
    finally:
        event.remove(engine, "checkout", reject_connection)


@pytest.mark.parametrize("environment", ["development", "test"])
def test_nonproduction_startup_preserves_demo_seed(monkeypatch, sessions, environment):
    with start_app(monkeypatch, sessions, environment):
        with sessions() as db:
            admin = db.query(User).one()
            assert admin.role == "admin"
            assert admin.email == "admin@ticketdesk.enterprise"


def test_bootstrap_command_prompts_hashes_and_allows_admin_login(monkeypatch, ready_db, capsys):
    monkeypatch.setattr(bootstrap_admin, "SessionLocal", ready_db)
    prompts = []

    def hidden_input(prompt):
        prompts.append(prompt)
        return PASSWORD

    monkeypatch.setattr(bootstrap_admin, "getpass", hidden_input)
    assert bootstrap_admin.main(["--email", "Owner@Example.com", "--full-name", "POC Administrator"]) == 0
    assert len(prompts) == 2
    with ready_db() as db:
        admin = db.query(User).one()
        assert admin.email == "owner@example.com"
        assert admin.role == "admin"
        assert admin.session_identity
        assert admin.hashed_password != PASSWORD
        assert verify_password(PASSWORD, admin.hashed_password)
        audit = db.query(AuditLog).filter_by(action=BOOTSTRAP_ACTION).one()
        assert audit.entity_id == str(admin.id)
        assert audit.metadata_json == "{}"
        output = capsys.readouterr()
        assert PASSWORD not in output.out + output.err
        assert admin.hashed_password not in output.out + output.err

    with start_app(monkeypatch, ready_db, "production") as client:
        response = client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
        assert response.status_code == 200
        user_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"})
        assert user_response.status_code == 200
        assert user_response.json()["role"] == "admin"


def test_bootstrap_refuses_existing_identity_without_elevating(ready_db):
    with ready_db.begin() as db:
        employee = db.query(Role).filter_by(name="employee").one()
        db.add(User(email="Owner@Example.com", full_name="Original User", role_id=employee.id, hashed_password="original-hash"))
    with pytest.raises(BootstrapError, match="identity already belongs"):
        provision(ready_db)
    with ready_db() as db:
        existing = db.query(User).one()
        assert (existing.full_name, existing.role, existing.hashed_password) == ("Original User", "employee", "original-hash")
        assert db.query(AuditLog).count() == 0


@pytest.mark.parametrize(("email", "password", "error"), [
    ("invalid-email", PASSWORD, "valid administrator email"),
    ("owner@example.com", "too-short", "at least 16 characters"),
    ("owner@example.com", "é" * 37, "72 UTF-8 bytes"),
])
def test_bootstrap_rejects_invalid_identity_or_password(ready_db, email, password, error):
    with pytest.raises(BootstrapError, match=error):
        provision(ready_db, email=email, password=password)
    with ready_db() as db:
        assert db.query(User).count() == 0


@pytest.mark.parametrize("names", [[], ["ADMIN"], ["admin", "ADMIN"]])
def test_bootstrap_refuses_missing_invalid_or_ambiguous_role(sessions, names):
    with sessions.begin() as db:
        db.add_all([Role(name=name, display_name="Administrator") for name in names])
    with pytest.raises(BootstrapError, match="role is missing, invalid, or ambiguous"):
        provision(sessions)
    with sessions() as db:
        assert db.query(User).count() == 0


def test_bootstrap_rerun_preserves_existing_admin(ready_db):
    provision(ready_db)
    with ready_db() as db:
        original = db.query(User).one().hashed_password
    with pytest.raises(BootstrapError, match="identity already belongs"):
        provision(ready_db, password="different-passphrase-1")
    with pytest.raises(BootstrapError, match="administrator already exists"):
        provision(ready_db, email="second@example.com")
    with ready_db() as db:
        existing = db.query(User).one()
        assert existing.role == "admin"
        assert existing.hashed_password == original
        assert db.query(AuditLog).filter_by(action=BOOTSTRAP_ACTION).count() == 1


def test_bootstrap_rejects_unsafe_terminal_input(monkeypatch, ready_db, capsys):
    def visible_input(_prompt):
        warnings.warn("Password input would be visible", GetPassWarning)

    monkeypatch.setattr(bootstrap_admin, "SessionLocal", ready_db)
    monkeypatch.setattr(bootstrap_admin, "getpass", visible_input)
    args = ["--email", "owner@example.com", "--full-name", "POC Administrator"]
    assert bootstrap_admin.main(args) == 1
    assert "hidden password input" in capsys.readouterr().err
    with pytest.raises(SystemExit) as error:
        bootstrap_admin.main([*args, "--password", PASSWORD])
    assert error.value.code == 2
    assert PASSWORD not in capsys.readouterr().err
    with ready_db() as db:
        assert db.query(User).count() == 0


@pytest.mark.parametrize("emails", [
    ("owner@example.com", "Owner@example.com"),
    ("owner@example.com", "second@example.com"),
])
def test_concurrent_bootstrap_allows_exactly_one_admin(ready_db, emails):
    start = Barrier(2)

    def attempt(email):
        start.wait(timeout=5)
        try:
            provision(ready_db, email=email)
            return True
        except BootstrapError:
            return False

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(attempt, emails)) == [False, True]
    with ready_db() as db:
        assert db.query(User).one().role == "admin"
        assert db.query(AuditLog).filter_by(action=BOOTSTRAP_ACTION).count() == 1
