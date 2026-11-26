"""System-generated password recovery tickets for unauthenticated requests."""

from datetime import datetime, timezone

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.organization import SupportTeam
from app.models.ticket import Ticket, TicketCategory, TicketHistory
from app.models.user import User
from app.services.audit_service import create_notification, record_audit_log
from app.services.sla_service import apply_sla_policy_to_ticket
from app.services.ticket_workflow import (
    finalize_ticket_number,
    provisional_ticket_number,
)


def password_recovery_role_label(user: User) -> str:
    """Use actual role and job title for the recovery ticket."""
    if user.role == "admin":
        return "Administrator"
    if user.role == "employee":
        return "Employee"
    if user.role == "agent":
        return (user.job_title or "").strip() or "IT Support Agent"
    return user.role.replace("_", " ").title()


def create_password_recovery_ticket(
    db: Session,
    email: str,
    employee_id: str,
    reason: str,
    client_ip: str,
) -> bool:
    """Create one unverified Critical recovery ticket per active request."""

    normalized_email = email.strip().lower()
    normalized_employee_id = employee_id.strip().lower()
    clean_reason = " ".join(reason.split())

    if (
        not normalized_email
        or not normalized_employee_id
        or len(clean_reason) < 10
        or len(clean_reason) > 500
    ):
        return False

    user = db.query(User).filter(
        func.lower(User.email) == normalized_email,
        func.lower(User.employee_id) == normalized_employee_id,
        User.is_active.is_(True),
    ).first()

    # Never reveal whether an account exists.
    if user is None:
        return False

    category = db.query(TicketCategory).filter(
        TicketCategory.slug == "access",
        TicketCategory.is_active.is_(True),
    ).first()

    team = db.query(SupportTeam).filter(
        SupportTeam.code == "IAM",
        SupportTeam.is_active.is_(True),
    ).first()

    if category is None or team is None:
        raise RuntimeError("Password recovery category or IAM team unavailable")

    try:
        # PostgreSQL transaction lock prevents concurrent duplicate tickets.
        db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "CAST(:namespace AS integer), CAST(:user_id AS integer))"
            ),
            {"namespace": 170011, "user_id": user.id},
        )

        existing = db.query(Ticket.id).filter(
            Ticket.requester_id == user.id,
            Ticket.category_id == category.id,
            Ticket.subcategory == "Password Reset",
            Ticket.status.in_(("open", "assigned", "in_progress", "pending")),
            Ticket.transferred_at.is_(None),
        ).first()

        if existing:
            db.commit()
            return True

        now = datetime.now(timezone.utc)

        role_label = password_recovery_role_label(user)
        account_id = user.employee_id or f"User-{user.id}"

        ticket = Ticket(
            ticket_number=provisional_ticket_number(),
            subject=(
                f"{account_id} - {user.full_name} ({role_label}) "
                "- Password Reset Required"
            ),
            description=(
                "Dear Administrator,\n\n"
                "A password reset request has been submitted for the "
                "following TicketDesk account:\n\n"
                f"Name: {user.full_name}\n"
                f"ID: {account_id}\n"
                f"Role: {role_label}\n"
                f"Email: {user.email}\n\n"
                "Request: I would like to request a password reset "
                "for my TicketDesk account.\n"
                f"Reason: {clean_reason}\n\n"
                "Please review my request and assist me after "
                "independently verifying my identity.\n\n"
                "Thank you."
            ),
            category_id=category.id,
            subcategory="Password Reset",
            priority="critical",
            status="open",
            requester_id=user.id,
            assigned_agent_id=None,
            department_id=user.department_id,
            support_team_id=team.id,
            affected_service="TicketDesk Account Access",
            sla_started_at=now,
            team_received_at=now,
            created_at=now,
            updated_at=now,
        )

        apply_sla_policy_to_ticket(db, ticket, base_time=now)
        db.add(ticket)
        db.flush()
        finalize_ticket_number(db, ticket)

        db.add(
            TicketHistory(
                ticket_id=ticket.id,
                actor_id=None,
                action="CREATED",
                field_name="status",
                old_value=None,
                new_value="open",
                description=(
                    "System created an unverified password recovery request. "
                    "Identity verification is required before any reset."
                ),
                created_at=now,
            )
        )

        staff = db.query(User).filter(User.is_active.is_(True)).all()

        for member in staff:
            if member.role == "admin" or (
                member.role == "agent"
                and member.support_team_id == team.id
            ):
                create_notification(
                    db=db,
                    user_id=member.id,
                    ticket_id=ticket.id,
                    title=f"[CRITICAL] Password Recovery {ticket.ticket_number}",
                    message=(
                        "An unverified account recovery request needs "
                        "identity verification and administrator review."
                    ),
                    notification_type="new_ticket_queue",
                )

        record_audit_log(
            db=db,
            user_id=None,
            action="PASSWORD_RECOVERY_TICKET_CREATED",
            entity_type="ticket",
            entity_id=ticket.ticket_number,
            metadata={
                "ticket_id": ticket.id,
                "requester_id": user.id,
                "source": "public_forgot_password",
                "identity_verified": False,
            },
            ip_address=client_ip,
        )

        db.commit()
        return True

    except Exception:
        db.rollback()
        raise
