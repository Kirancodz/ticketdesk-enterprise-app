import pytest
from sqlalchemy import func
from test_sla_alerts import setup  # Reuse the isolated in-memory API/database fixture.
from app.models.organization import Department, SupportTeam
from app.models.user import User
from app.models.system import AuditLog


def create(client, headers, role, email, **extra):
    return client.post("/api/v1/users", headers=headers("admin"), json={
        "email": email, "password": "TestPassword123!", "full_name": "Created User", "role": role, **extra,
    })


@pytest.mark.parametrize("role", ["employee", "agent", "admin"])
def test_three_roles_create_login_and_permissions(setup, role):
    db, client, users, team, ticket, headers = setup
    response = create(client, headers, role, f"new.{role}@example.com", job_title="Specialist", support_team_id=team.id)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["role"] == role and data["job_title"] == "Specialist"
    assert data["support_team_id"] == team.id
    login = client.post("/api/v1/auth/login", json={"email": data["email"], "password": "TestPassword123!"})
    assert login.status_code == 200 and login.json()["user"]["role"] == role
    assert login.json()["user"]["must_change_password"] is True
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # New accounts cannot access protected features before changing password.
    assert client.get("/api/v1/dashboard/summary", headers=auth).status_code == 403

    changed = client.post(
        "/api/v1/auth/change-password",
        headers=auth,
        json={
            "current_password": "TestPassword123!",
            "new_password": "RotatedPassword123!",
            "confirm_password": "RotatedPassword123!",
        },
    )
    assert changed.status_code == 200, changed.text

    # Previous access token must become invalid.
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 401

    relogin = client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": "RotatedPassword123!"},
    )
    assert relogin.status_code == 200, relogin.text
    assert relogin.json()["user"]["must_change_password"] is False

    auth = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
    assert client.get("/api/v1/dashboard/summary", headers=auth).status_code == 200
    assert client.get("/api/v1/users", headers=auth).status_code == (200 if role == "admin" else 403)
    assert client.get("/api/v1/notifications/sla-alerts", headers=auth).status_code == (200 if role == "admin" else 403)


def test_inline_organization_creation_reuse_and_retry(setup):
    db, client, users, team, ticket, headers = setup
    first = create(client, headers, "agent", "inline1@example.com", department_name="  Research  ", support_team_name="  Research IT  ")
    assert first.status_code == 201, first.text
    one = first.json()
    assert one["department"]["name"] == "Research" and one["support_team"]["name"] == "Research IT"
    second = create(client, headers, "admin", "inline2@example.com", department_name="research", support_team_name="research it")
    assert second.status_code == 201, second.text
    assert second.json()["department_id"] == one["department_id"]
    assert second.json()["support_team_id"] == one["support_team_id"]
    retry = create(client, headers, "agent", "inline1@example.com", department_name="Do Not Create", support_team_name="Do Not Create IT")
    assert retry.status_code == 409
    assert db.query(Department).filter(Department.name == "Do Not Create").count() == 0
    assert db.query(SupportTeam).filter(func.lower(SupportTeam.name) == "research it").count() == 1
    assert len(one["department"]["code"]) <= 30


@pytest.mark.parametrize("extra", [
    {"department_name": "   "}, {"support_team_name": "x"}, {"department_name": "x" * 121},
])
def test_invalid_inline_names_rejected(setup, extra):
    db, client, users, team, ticket, headers = setup
    response = create(client, headers, "agent", "invalid@example.com", **extra)
    assert response.status_code == 422
    assert db.query(User).filter(User.email == "invalid@example.com").count() == 0


def test_atomic_organization_validation_and_employee_organizations(setup):
    db, client, users, team, ticket, headers = setup
    response = create(client, headers, "agent", "invalid@example.com", department_name="Rollback Department", support_team_id=999999)
    assert response.status_code == 400
    assert db.query(Department).filter(Department.name == "Rollback Department").count() == 0
    assert db.query(AuditLog).filter(AuditLog.entity_type == "department").count() == 0
    response = create(client, headers, "agent", "conflict@example.com", support_team_id=team.id, support_team_name="Conflicting Team")
    assert response.status_code == 400
    employee = create(client, headers, "employee", "plain.employee@example.com", department_name="Employee Department", support_team_id=team.id, job_title="Employee Title")
    assert employee.status_code == 201
    assert employee.json()["department"]["name"] == "Employee Department"
    assert employee.json()["support_team_id"] == team.id
    optional = create(client, headers, "employee", "optional.employee@example.com")
    assert optional.status_code == 201 and optional.json()["department_id"] is None and optional.json()["support_team_id"] is None
    denied = client.post("/api/v1/users", headers=headers("agent"), json={"email": "denied@example.com", "password": "Test123!", "full_name": "Denied", "role": "admin", "department_name": "Forbidden Department"})
    assert denied.status_code == 403
    assert db.query(Department).filter(Department.name == "Forbidden Department").count() == 0


def test_inline_inactive_organization_is_not_silently_reactivated(setup):
    db, client, users, team, ticket, headers = setup
    team.is_active = False
    db.commit()
    response = create(client, headers, "agent", "inactive@example.com", support_team_name="test team")
    assert response.status_code == 409
    assert db.query(SupportTeam).count() == 1
