from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import csv
import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models.organization import Role, SupportTeam
from app.models.ticket import Ticket, TicketCategory, TicketTransferLink, TicketWorkRecord, TicketHistory
from app.models.user import User


@pytest.fixture()
def workflow(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'workflow.db'}", connect_args={"check_same_thread": False, "timeout": 15})
    @event.listens_for(engine, "connect")
    def fk(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    roles = {name: Role(name=name, display_name=name) for name in ("admin", "employee", "agent")}
    teams = {name: SupportTeam(name=name, code=name.upper()) for name in ("software", "cloud")}
    db.add_all([*roles.values(), *teams.values()]); db.flush()
    users = {}
    for name, role, team in [("admin", "admin", None), ("employee", "employee", None), ("outsider", "employee", None), ("softA", "agent", "software"), ("softB", "agent", "software"), ("cloudA", "agent", "cloud"), ("cloudB", "agent", "cloud")]:
        users[name] = User(full_name=name, email=f"{name.lower()}@example.com", hashed_password="unused", role_id=roles[role].id, support_team_id=teams[team].id if team else None)
    category = TicketCategory(name="Software", slug="software")
    db.add_all([*users.values(), category]); db.commit()
    user_ids = {name: u.id for name, u in users.items()}
    team_ids = {name: t.id for name, t in teams.items()}
    tokens = {name: {"Authorization": f"Bearer {create_access_token(u.id, u.role, session_identity=u.session_identity)}"} for name, u in users.items()}
    category_id = category.id
    db.close()
    def override():
        session = factory()
        try: yield session
        finally: session.close()
    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    def request(method, path, actor, **kwargs):
        return client.request(method, f"/api/v1{path}", headers=tokens[actor], **kwargs)
    def create():
        response = request("POST", "/tickets", "employee", json={"subject": "Software issue needs support", "description": "Application cannot connect to its backend service", "category_id": category_id, "support_team_id": team_ids["software"], "priority": "high"})
        assert response.status_code == 201, response.text
        return response.json()
    yield request, create, factory, user_ids, team_ids
    client.close(); app.dependency_overrides.clear(); engine.dispose()


def test_team_isolation_atomic_claim_chat_and_explicit_close(workflow):
    request, create, factory, users, teams = workflow
    ticket = create(); tid = ticket["id"]
    for name in ("softA", "softB"):
        assert request("GET", "/tickets", name).json()["total"] == 1
    assert request("GET", f"/tickets?unassigned_only=true&support_team_id={teams['software']}", "cloudA").json()["total"] == 0
    assert request("GET", f"/tickets/{tid}", "cloudA").status_code == 403
    assert request("GET", "/dashboard/summary", "cloudA").json()["total_tickets"] == 0
    assert request("GET", "/notifications", "cloudA").json()["total"] == 0
    assert request("POST", f"/tickets/{tid}/comments", "softA", json={"body": "Cannot chat before acceptance"}).status_code == 403
    barrier = Barrier(2)
    def claim(actor):
        barrier.wait()
        return actor, request("POST", f"/tickets/{tid}/accept", actor)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(claim, ["softA", "softB"]))
    assert sorted(response.status_code for _, response in responses) == [200, 409]
    owner = next(actor for actor, response in responses if response.status_code == 200)
    peer = "softA" if owner == "softB" else "softB"
    assert request("GET", "/tickets", owner).json()["total"] == 0
    assert request("GET", "/tickets?my_tickets=true", owner).json()["total"] == 1
    assert request("GET", "/tickets", peer).json()["total"] == 0
    assert request("GET", "/notifications", peer).json()["total"] == 0
    assert request("GET", f"/tickets/{tid}", peer).status_code == 403
    assert request("POST", f"/tickets/{tid}/accept", owner).status_code == 200
    assert request("PATCH", f"/tickets/{tid}/status", owner, json={"status": "in_progress"}).status_code == 200
    state = request("GET", f"/tickets/{tid}", "employee").json()
    assert state["status"] == "in_progress" and state["assigned_agent"]["id"] == users[owner]
    assert state["work_started_at"]
    assert request("POST", f"/tickets/{tid}/comments", "employee", json={"body": "We agree it is solved. Please close."}).status_code == 201
    assert request("POST", f"/tickets/{tid}/comments", owner, json={"body": "Confirmed fix and completed work."}).status_code == 201
    assert request("POST", f"/tickets/{tid}/comments", owner, json={"body": "Private diagnostic", "is_internal": True}).status_code == 201
    state = request("GET", f"/tickets/{tid}", "employee").json()
    assert state["status"] == "in_progress"
    assert len(state["comments"]) == 2
    assert request("PATCH", f"/tickets/{tid}/status", "employee", json={"status": "closed"}).status_code == 403
    assert request("GET", f"/tickets/{tid}", "outsider").status_code == 403
    assert request("PATCH", f"/tickets/{tid}/status", owner, json={"status": "closed"}).status_code == 200
    assert request("GET", f"/tickets/{tid}", "employee").json()["status"] == "closed"
    with factory() as db:
        assert db.query(TicketHistory).filter_by(ticket_id=tid, action="ACCEPTED").count() == 1
        assert db.query(TicketWorkRecord).filter_by(ticket_id=tid).count() == 1


def test_transfer_lineage_sla_continuity_personal_reports_and_export(workflow):
    request, create, factory, users, teams = workflow
    original = create(); tid = original["id"]
    request("POST", f"/tickets/{tid}/accept", "softA")
    request("PATCH", f"/tickets/{tid}/status", "softA", json={"status": "in_progress"})
    request("POST", f"/tickets/{tid}/comments", "employee", json={"body": "Original employee discussion"})
    request("POST", f"/tickets/{tid}/comments", "softA", json={"body": "Software diagnostics complete; network fault suspected"})
    payload = {"support_team_id": teams["cloud"], "assigned_agent_id": users["cloudA"], "reason": "Software verified; cloud network diagnosis required"}
    invalid = dict(payload, assigned_agent_id=users["softB"])
    assert request("POST", f"/tickets/{tid}/transfer", "softA", json=invalid).status_code == 400
    result = request("POST", f"/tickets/{tid}/transfer", "softA", json=payload)
    assert result.status_code == 200, result.text
    successor = result.json(); sid = successor["id"]
    retry = request("POST", f"/tickets/{tid}/transfer", "softA", json=payload)
    assert retry.status_code == 200 and retry.json()["id"] == sid
    old = request("GET", f"/tickets/{tid}", "employee").json()
    new = request("GET", f"/tickets/{sid}", "cloudA").json()
    assert old["status"] == "closed" and old["sla"]["resolved_at"] is None
    assert request("GET", "/dashboard/summary", "softA").json()["transferred_tickets"] == 1
    assert request("GET", "/dashboard/summary", "cloudA").json()["transferred_tickets"] == 0
    assert request("GET", "/dashboard/summary", "admin").json()["transferred_tickets"] == 1
    distribution = request("GET", "/dashboard/distribution", "admin").json()
    status_counts = {item["key"]: item["value"] for item in distribution["by_status"]}
    assert status_counts["transferred"] == 1
    assert status_counts["closed"] == 0
    assert sum(status_counts.values()) == 2
    assert old["closed_at"] and old["transfer_outcome"] == "transferred" and old["sla"]["sla_health"] == "closed"
    assert new["status"] == "open" and new["requester"]["id"] == users["employee"]
    assert new["original_submitted_at"] == original["original_submitted_at"]
    assert new["sla"]["resolution_due_at"] == original["sla"]["resolution_due_at"]
    assert new["sla"]["first_response_due_at"] == original["sla"]["first_response_due_at"]
    assert new["team_received_at"] >= old["team_received_at"] and new["work_started_at"] is None
    assert any(link["id"] == tid and link["can_open"] for link in new["lineage"])
    prior = request("GET", f"/tickets/{tid}", "cloudA").json()
    assert any(comment["body"] == "Original employee discussion" for comment in prior["comments"])
    assert any(item["action"] == "STATUS_CHANGED" for item in prior["history"])
    assert request("GET", f"/tickets/{sid}", "cloudB").status_code == 403
    assert request("GET", "/tickets?assigned_to_me=true", "softA").json()["total"] == 0
    assert request("POST", f"/tickets/{tid}/comments", "softA", json={"body": "late note"}).status_code == 409
    assert request("POST", f"/tickets/{sid}/accept", "cloudA").status_code == 200
    assert request("PATCH", f"/tickets/{sid}/status", "cloudA", json={"status": "in_progress"}).status_code == 200
    assert request("PATCH", f"/tickets/{sid}/status", "cloudA", json={"status": "closed"}).status_code == 200
    for actor, expected_id, forbidden_number in [("softA", tid, new["ticket_number"]), ("cloudA", sid, old["ticket_number"])]:
        data = request("GET", "/reports/tickets?role=admin&user_id=1&scope=all", actor).json()
        assert data["total_tickets"] == 1 and data["distinct_requests"] == 1
        assert [row["id"] for row in data["records"]] == [expected_id]
        exported = request("GET", "/reports/export/csv?assigned_agent_id=1&scope=all", actor)
        rows = list(csv.DictReader(io.StringIO(exported.text)))
        assert len(rows) == 1 and forbidden_number not in exported.text
        performance = request("GET", "/reports/agents?user_id=1", actor).json()
        assert len(performance) == 1 and performance[0]["agent_id"] == users[actor]
    assert request("GET", "/reports/tickets", "softB").json()["total_tickets"] == 0
    assert request("GET", "/reports/sla", "softB").json()["total_evaluated"] == 0
    aggregate = request("GET", "/reports/tickets", "admin").json()
    assert aggregate["total_tickets"] == 2 and aggregate["distinct_requests"] == 1 and aggregate["transferred_count"] == 1
    assert aggregate["open_vs_closed"]["active"] == 0
    assert request("GET", "/reports/sla", "admin").json()["total_evaluated"] == 1
    assert len(list(csv.DictReader(io.StringIO(request("GET", "/reports/export/csv", "admin").text)))) == 2
    with factory() as db:
        assert db.query(TicketTransferLink).count() == 1
        assert db.query(TicketWorkRecord).filter_by(ticket_id=tid, user_id=users["softA"], outcome="transferred").count() == 1


def test_concurrent_transfer_creates_only_one_successor(workflow):
    request, create, factory, users, teams = workflow
    original = create(); tid = original["id"]
    request("POST", f"/tickets/{tid}/accept", "softA")
    payload = {"support_team_id": teams["cloud"], "reason": "Cloud specialty needed after diagnostics"}
    barrier = Barrier(2)
    def transfer(_):
        barrier.wait()
        return request("POST", f"/tickets/{tid}/transfer", "softA", json=payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(transfer, range(2)))
    assert all(response.status_code in (200, 409) for response in responses)
    assert any(response.status_code == 200 for response in responses)
    with factory() as db:
        assert db.query(TicketTransferLink).count() == 1
        assert db.query(Ticket).count() == 2
    link = next(response.json() for response in responses if response.status_code == 200)
    request("POST", f"/tickets/{link['id']}/accept", "cloudA")
    third = request("POST", f"/tickets/{link['id']}/transfer", "cloudA", json={"support_team_id": teams["software"], "assigned_agent_id": users["softB"], "reason": "Network validated; return to software specialist"}).json()
    final = request("GET", f"/tickets/{third['id']}", "softB").json()
    assert final["sla"]["resolution_due_at"] == original["sla"]["resolution_due_at"]
    assert len(final["lineage"]) == 2
    for ancestor in final["lineage"]:
        assert request("GET", f"/tickets/{ancestor['id']}", "softB").status_code == 200


def test_independent_authenticated_requests_keep_jwt_subject_on_navigation(workflow):
    request, create, factory, users, teams = workflow
    with ThreadPoolExecutor(max_workers=2) as pool:
        identities = list(pool.map(lambda actor: request("GET", "/auth/me", actor).json(), ["admin", "employee"]))
    assert {row["id"] for row in identities} == {users["admin"], users["employee"]}
    assert request("GET", "/settings", "admin").status_code == 200
    assert request("GET", "/auth/me", "admin").json()["role"] == "admin"
    create()
    assert request("GET", "/auth/me", "employee").json()["id"] == users["employee"]


def test_deleted_user_id_reuse_cannot_reauthenticate_as_a_different_account(workflow):
    request, create, factory, users, teams = workflow
    old_id = users["cloudB"]
    with factory() as db:
        old = db.get(User, old_id)
        old_identity = old.session_identity
        db.delete(old); db.commit()
        admin_role = db.query(Role).filter_by(name="admin").one()
        replacement = User(full_name="Different Account", email="replacement@example.com", hashed_password="unused", role_id=admin_role.id)
        db.add(replacement); db.commit()
        assert replacement.id == old_id  # Reproduces SQLite's real numeric-ID reuse.
        assert replacement.session_identity != old_identity
    response = request("GET", "/auth/me", "cloudB")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_IDENTITY_CHANGED"


def test_role_changes_require_explicit_sign_in_for_access_and_refresh(workflow):
    from datetime import datetime, timedelta, timezone
    from app.models.user import RefreshToken
    from app.core.security import hash_token
    request, create, factory, users, teams = workflow
    with factory() as db:
        actor = db.get(User, users["cloudA"])
        db.add(RefreshToken(user_id=actor.id, token_hash=hash_token("test-role-refresh"),
            session_identity=actor.session_identity, role_at_issue="agent", expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
        actor.role_id = db.query(Role).filter_by(name="admin").one().id
        db.commit()
    assert request("GET", "/auth/me", "cloudA").status_code == 401
    assert request("POST", "/auth/refresh", "cloudA", json={"refresh_token": "test-role-refresh"}).status_code == 401

def test_reassignment_retains_work_without_claiming_someone_elses_resolution(workflow):
    request, create, factory, users, teams = workflow
    ticket = create(); tid = ticket["id"]
    request("POST", f"/tickets/{tid}/accept", "softA")
    request("PATCH", f"/tickets/{tid}/status", "softA", json={"status": "in_progress"})
    assert request("PATCH", f"/tickets/{tid}/assign", "admin", json={"assigned_agent_id": users["softB"]}).status_code == 200
    assert request("PATCH", f"/tickets/{tid}/status", "softB", json={"status": "closed"}).status_code == 200
    previous = request("GET", "/reports/tickets", "softA").json()
    assert previous["total_tickets"] == 1 and previous["records"][0]["work_outcome"] == "reassigned"
    assert previous["open_vs_closed"]["resolved_or_closed"] == 0 and previous["open_vs_closed"]["active"] == 0
    own = request("GET", "/reports/agents", "softA").json()[0]
    assert own["resolved_count"] == 0 and own["pending_workload"] == 0


def test_admin_escalation_accept_or_reject_and_redirect(workflow):
    request, create, factory, users, teams = workflow
    original = create(); tid = original["id"]
    request("POST", f"/tickets/{tid}/accept", "softA")
    escalation = request("POST", f"/tickets/{tid}/transfer", "softA", json={"escalate_to_admin": True, "assigned_agent_id": users["admin"], "reason": "Administrator approval and specialist routing needed"})
    assert escalation.status_code == 200, escalation.text
    eid = escalation.json()["id"]
    inbox = request("GET", "/tickets?assigned_to_me=true", "admin").json()
    assert [row["id"] for row in inbox["items"]] == [eid]
    assert inbox["items"][0]["routed_by"]["id"] == users["softA"]
    assert request("GET", "/tickets?my_tickets=true", "admin").json()["total"] == 0
    redirected = request("POST", f"/tickets/{eid}/transfer", "admin", json={"reject_assignment": True, "support_team_id": teams["cloud"], "reason": "Declined escalation; route to cloud specialists"})
    assert redirected.status_code == 200, redirected.text
    assert request("GET", "/tickets?assigned_to_me=true", "admin").json()["total"] == 0
    assert request("GET", "/tickets?my_tickets=true", "admin").json()["total"] == 0
    target_id = redirected.json()["id"]
    assert request("GET", "/tickets", "cloudA").json()["items"][0]["id"] == target_id
    assert request("GET", f"/tickets/{target_id}", "employee").json()["sla"]["resolution_due_at"] == original["sla"]["resolution_due_at"]
    assert request("GET", f"/tickets/{eid}", "employee").json()["status"] == "closed"
    next_ticket = create(); nid = next_ticket["id"]
    request("POST", f"/tickets/{nid}/accept", "softB")
    next_escalation = request("POST", f"/tickets/{nid}/transfer", "softB", json={"escalate_to_admin": True, "assigned_agent_id": users["admin"], "reason": "Administrator action requested on this ticket"}).json()
    assert request("POST", f"/tickets/{next_escalation['id']}/accept", "admin").status_code == 200
    assert request("GET", "/tickets?assigned_to_me=true", "admin").json()["total"] == 0
    assert [row["id"] for row in request("GET", "/tickets?my_tickets=true", "admin").json()["items"]] == [next_escalation["id"]]


def test_live_overdue_count_and_daily_cumulative_alerts_survive_closure(workflow):
    from datetime import datetime, timedelta, timezone
    from app.services.analytics_service import sla_alerts_today
    request, create, factory, users, teams = workflow
    ticket = create(); tid = ticket["id"]
    with factory() as db:
        row = db.get(Ticket, tid)
        row.resolution_due_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.commit()
    summary = request("GET", "/dashboard/summary", "admin").json()
    assert summary["overdue_tickets"] == request("GET", "/notifications/sla-alerts", "admin").json()["total"] == 1
    assert summary["sla_alerts_today"] == 1
    request("POST", f"/tickets/{tid}/accept", "softA")
    request("PATCH", f"/tickets/{tid}/status", "softA", json={"status":"closed"})
    completed = request("GET", "/dashboard/summary", "admin").json()
    assert completed["overdue_tickets"] == 0 and completed["sla_alerts_today"] == 1
    detail = request("GET", f"/tickets/{tid}", "employee").json()
    assert detail["sla"]["sla_health"] == "closed" and detail["sla"]["resolution_breached"] is True
    with factory() as db:
        assert sla_alerts_today(db, datetime.now(timezone.utc)+timedelta(days=1)) == 0


def test_legacy_transfers_migrate_to_closed_with_an_audit_event(workflow, monkeypatch):
    from pathlib import Path
    from datetime import datetime, timezone
    from alembic import command
    from alembic.config import Config
    from app.core.config import settings
    from app.models.system import AuditLog
    request, create, factory, users, teams = workflow
    original = create()
    with factory() as db:
        row = db.get(Ticket, original["id"])
        row.status = "transferred"
        row.transferred_at = datetime.now(timezone.utc)
        db.commit()
        url = "sqlite:///" + Path(db.bind.url.database).as_posix()
    backend = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "migrations"))
    command.stamp(cfg, "0004_stable_account_sessions")
    command.upgrade(cfg, "0005_transfer_segment_closure")
    with factory() as db:
        row = db.get(Ticket, original["id"])
        assert row.status == "closed" and row.closed_at and row.resolved_at is None
        assert db.query(AuditLog).filter_by(action="TRANSFER_CLOSURE_NORMALIZED", entity_id=row.ticket_number).count() == 1
    visible = request("GET", f"/tickets/{original['id']}", "employee").json()
    assert visible["status"] == "closed" and visible["transfer_outcome"] == "transferred"
    assert visible["sla"]["sla_health"] == "closed"


def test_admin_sees_unclaimed_system_password_recovery(workflow):
    from datetime import datetime, timezone

    request, create, factory, users, teams = workflow

    normal = create()
    recovery = create()
    lookalike = create()

    with factory() as db:
        iam = SupportTeam(
            name="Identity and Access Management",
            code="IAM",
            is_active=True,
        )
        db.add(iam)
        db.flush()

        for ticket_id in (recovery["id"], lookalike["id"]):
            ticket = db.get(Ticket, ticket_id)
            ticket.support_team_id = iam.id
            ticket.subcategory = "Password Reset"
            ticket.priority = "critical"
            ticket.status = "open"

        db.add(TicketHistory(
            ticket_id=recovery["id"],
            actor_id=None,
            action="CREATED",
            field_name="status",
            old_value=None,
            new_value="open",
            description=(
                "System created an unverified password recovery request. "
                "Identity verification is required before any reset."
            ),
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()

    response = request("GET", "/tickets?my_tickets=true", "admin")
    assert response.status_code == 200, response.text

    ids = [item["id"] for item in response.json()["items"]]

    assert ids == [recovery["id"]], ids
    assert normal["id"] not in ids
    assert lookalike["id"] not in ids

    all_response = request("GET", "/tickets", "admin")
    assert all_response.status_code == 200
    all_ids = [item["id"] for item in all_response.json()["items"]]
    assert all_ids.count(recovery["id"]) == 1


@pytest.mark.parametrize(
    "role,job_title,expected",
    [
        ("employee", None, "Employee"),
        ("agent", "IT Consultant", "IT Consultant"),
        ("agent", "Cloud Engineer", "Cloud Engineer"),
        ("agent", None, "IT Support Agent"),
        ("admin", "Director", "Administrator"),
    ],
)
def test_password_recovery_role_label_uses_actual_designation(
    role, job_title, expected
):
    from types import SimpleNamespace
    from app.services.password_recovery_service import (
        password_recovery_role_label,
    )

    user = SimpleNamespace(role=role, job_title=job_title)
    assert password_recovery_role_label(user) == expected
