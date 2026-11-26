import secrets
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.core.deps import get_current_user, require_admin, require_agent_or_admin
from app.core.exceptions import AppException
from app.core.security import get_password_hash
from app.middleware.rate_limit import get_client_ip
from app.models.organization import Department, Role, SupportTeam
from app.models.ticket import Ticket, TicketAttachment, TicketCategory, TicketComment, TicketHistory
from app.models.user import RefreshToken, User
from app.schemas.auth import DepartmentInfo, SupportTeamInfo, UserRoleInfo
from app.schemas.user import (
    AdminPasswordResetRequest,
    DepartmentCreateRequest,
    PaginatedUsersResponse,
    SupportTeamCreateRequest,
    UserCreateRequest,
    UserDetailResponse,
    UserRoleUpdateRequest,
    UserSummary,
    UserUpdateRequest,
)
from app.services.audit_service import record_audit_log
from app.services.organization_service import resolve_user_organization
from app.services.ticket_service import build_user_summary

router = APIRouter(prefix="/users", tags=["Users & Organization"])


def _serialize_user_detail(user: User) -> UserDetailResponse:
    return UserDetailResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        employee_id=user.employee_id,
        job_title=user.job_title,
        phone=user.phone,
        is_active=user.is_active,
        role=user.role,
        role_id=user.role_id,
        department_id=user.department_id,
        support_team_id=user.support_team_id,
        role_info=UserRoleInfo.model_validate(user.role_rel) if user.role_rel else None,
        department=DepartmentInfo.model_validate(user.department_rel) if user.department_rel else None,
        support_team=SupportTeamInfo.model_validate(user.support_team_rel) if user.support_team_rel else None,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("/departments", response_model=List[DepartmentInfo])
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[DepartmentInfo]:
    depts = db.query(Department).filter(Department.is_active == True).order_by(Department.name.asc()).all()  # noqa: E712
    return [DepartmentInfo.model_validate(d) for d in depts]


@router.post("/departments", response_model=DepartmentInfo, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DepartmentInfo:
    exists = (
        db.query(Department)
        .filter((Department.name == payload.name) | (Department.code == payload.code.upper()))
        .first()
    )
    if exists:
        raise AppException("Department with this name or code already exists.", status.HTTP_409_CONFLICT)

    dept = Department(
        name=payload.name.strip(),
        code=payload.code.strip().upper(),
        description=payload.description,
        location=payload.location,
        is_active=True,
    )
    db.add(dept)
    record_audit_log(
        db=db,
        user_id=current_user.id,
        action="DEPARTMENT_CREATED",
        entity_type="department",
        entity_id=dept.code,
        metadata={"name": dept.name},
    )
    db.commit()
    db.refresh(dept)
    return DepartmentInfo.model_validate(dept)


@router.get("/support-teams", response_model=List[SupportTeamInfo])
def list_support_teams(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[SupportTeamInfo]:
    teams = db.query(SupportTeam).filter(SupportTeam.is_active == True).order_by(SupportTeam.name.asc()).all()  # noqa: E712
    return [SupportTeamInfo.model_validate(t) for t in teams]


@router.post("/support-teams", response_model=SupportTeamInfo, status_code=status.HTTP_201_CREATED)
def create_support_team(
    payload: SupportTeamCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> SupportTeamInfo:
    exists = (
        db.query(SupportTeam)
        .filter((SupportTeam.name == payload.name) | (SupportTeam.code == payload.code.upper()))
        .first()
    )
    if exists:
        raise AppException("Support team with this name or code already exists.", status.HTTP_409_CONFLICT)

    team = SupportTeam(
        name=payload.name.strip(),
        code=payload.code.strip().upper(),
        description=payload.description,
        specialization=payload.specialization,
        is_active=True,
    )
    db.add(team)
    record_audit_log(
        db=db,
        user_id=current_user.id,
        action="SUPPORT_TEAM_CREATED",
        entity_type="support_team",
        entity_id=team.code,
        metadata={"name": team.name},
    )
    db.commit()
    db.refresh(team)
    return SupportTeamInfo.model_validate(team)


@router.delete("/support-teams/{team_id}")
def delete_support_team(
    team_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict:
    team = db.query(SupportTeam).filter(SupportTeam.id == team_id).first()
    if not team:
        raise AppException("Support team not found.", status.HTTP_404_NOT_FOUND)

    team_name = team.name
    team_code = team.code
    db.query(User).filter(User.support_team_id == team.id).update({"support_team_id": None})
    db.query(Ticket).filter(Ticket.support_team_id == team.id).update({"support_team_id": None})
    db.delete(team)

    record_audit_log(
        db=db,
        user_id=current_user.id,
        action="SUPPORT_TEAM_DELETED",
        entity_type="support_team",
        entity_id=team_code,
        metadata={"name": team_name},
        ip_address=get_client_ip(request),
    )
    db.commit()
    return {"success": True, "message": f"Support team '{team_name}' removed."}


@router.get("/agents", response_model=List[UserSummary])
def list_support_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agent_or_admin),
) -> List[UserSummary]:
    agents = (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(Role.name.in_(["agent", "admin"]), User.is_active == True)  # noqa: E712
        .order_by(User.full_name.asc())
        .all()
    )
    result = []
    for a in agents:
        summary = build_user_summary(a)
        if summary:
            result.append(summary)
    return result


@router.get("", response_model=PaginatedUsersResponse)
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    department_id: Optional[int] = Query(None),
    support_team_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> PaginatedUsersResponse:
    query = db.query(User).join(Role, User.role_id == Role.id)

    if role and role != "all":
        query = query.filter(Role.name == role)
    if department_id:
        query = query.filter(User.department_id == department_id)
    if support_team_id:
        query = query.filter(User.support_team_id == support_team_id)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.full_name.ilike(term),
                User.email.ilike(term),
                User.employee_id.ilike(term),
                User.job_title.ilike(term),
                User.phone.ilike(term),
            )
        )

    total = query.count()
    users = (
        query.order_by(User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [_serialize_user_detail(u) for u in users]
    total_pages = max(1, (total + page_size - 1) // page_size)

    return PaginatedUsersResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserDetailResponse:
    existing_email = (
        db.query(User)
        .filter(func.lower(User.email) == payload.email.lower().strip())
        .first()
    )
    if existing_email:
        raise AppException("A user with this email address already exists.", status.HTTP_409_CONFLICT, "EMAIL_EXISTS")

    if payload.employee_id and payload.employee_id.strip():
        existing_emp = db.query(User).filter(User.employee_id == payload.employee_id.strip()).first()
        if existing_emp:
            raise AppException("Employee ID is already assigned to another user.", status.HTTP_409_CONFLICT)

    role_obj = db.query(Role).filter(Role.name == payload.role).first()
    if not role_obj:
        raise AppException("Invalid role specified.", status.HTTP_400_BAD_REQUEST)

    try:
        now = datetime.now(timezone.utc)
        department_id = resolve_user_organization(db, Department, payload.department_id, payload.department_name, current_user.id)
        support_team_id = resolve_user_organization(db, SupportTeam, payload.support_team_id, payload.support_team_name, current_user.id)
        new_user = User(
            email=payload.email.lower().strip(),
            full_name=payload.full_name.strip(),
            employee_id=payload.employee_id.strip() if payload.employee_id and payload.employee_id.strip() else None,
            job_title=payload.job_title,
            phone=payload.phone.strip() if payload.phone and payload.phone.strip() else None,
            hashed_password=get_password_hash(payload.password),
            must_change_password=True,
            is_active=payload.is_active,
            role_id=role_obj.id,
            department_id=department_id,
            support_team_id=support_team_id,
            created_at=now,
            updated_at=now,
        )
        db.add(new_user)
        db.flush()

        record_audit_log(
            db=db,
            user_id=current_user.id,
            action="USER_CREATED",
            entity_type="user",
            entity_id=new_user.id,
            metadata={
                "email": new_user.email,
                "full_name": new_user.full_name,
                "role": payload.role,
                "phone": new_user.phone,
            },
            ip_address=get_client_ip(request),
        )
        db.commit()
        db.refresh(new_user)
        return _serialize_user_detail(new_user)
    except AppException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise AppException(
            "An account or organization with these details was created concurrently. Check the details and retry; no partial account or organization changes were saved.",
            status.HTTP_409_CONFLICT, "ACCOUNT_CREATION_CONFLICT",
        )


@router.put("/{user_id}", response_model=UserDetailResponse)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserDetailResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppException("User not found.", status.HTTP_404_NOT_FOUND)

    if payload.password is not None:
        raise AppException(
            "Use the dedicated Admin Reset Password action.",
            status.HTTP_400_BAD_REQUEST,
            "PASSWORD_RESET_ACTION_REQUIRED",
        )

    if payload.is_active is False and user.id == current_user.id:
        raise AppException("You cannot deactivate your own administrator account.", status.HTTP_400_BAD_REQUEST)

    changes = {}
    if payload.email is not None:
        email_clean = payload.email.lower().strip()
        if email_clean != user.email.lower():
            dup = db.query(User).filter(func.lower(User.email) == email_clean, User.id != user.id).first()
            if dup:
                raise AppException("Another user already uses this email address.", status.HTTP_409_CONFLICT)
            user.email = email_clean
            changes["email"] = user.email
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
        changes["full_name"] = user.full_name
    if payload.employee_id is not None:
        user.employee_id = payload.employee_id.strip() or None
        changes["employee_id"] = user.employee_id
    if payload.job_title is not None:
        user.job_title = payload.job_title
        changes["job_title"] = user.job_title
    if payload.phone is not None:
        user.phone = payload.phone.strip() or None
        changes["phone"] = user.phone
    if payload.department_id is not None:
        user.department_id = payload.department_id if payload.department_id > 0 else None
        changes["department_id"] = user.department_id
    if payload.support_team_id is not None:
        user.support_team_id = payload.support_team_id if payload.support_team_id > 0 else None
        changes["support_team_id"] = user.support_team_id
    if payload.is_active is not None:
        user.is_active = payload.is_active
        changes["is_active"] = user.is_active

    user.updated_at = datetime.now(timezone.utc)

    record_audit_log(
        db=db,
        user_id=current_user.id,
        action="USER_UPDATED",
        entity_type="user",
        entity_id=user.id,
        metadata={"email": user.email, "changes": changes},
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return _serialize_user_detail(user)


@router.patch("/{user_id}/role", response_model=UserDetailResponse)
def update_user_role(
    user_id: int,
    payload: UserRoleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserDetailResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppException("User not found.", status.HTTP_404_NOT_FOUND)

    if user.id == current_user.id and payload.role != "admin":
        raise AppException("Administrators cannot demote their own role.", status.HTTP_400_BAD_REQUEST)

    role_obj = db.query(Role).filter(Role.name == payload.role).first()
    if not role_obj:
        raise AppException("Role not found.", status.HTTP_400_BAD_REQUEST)

    old_role = user.role
    user.role_id = role_obj.id
    if payload.support_team_id is not None:
        user.support_team_id = payload.support_team_id if payload.support_team_id > 0 else None

    user.updated_at = datetime.now(timezone.utc)

    record_audit_log(
        db=db,
        user_id=current_user.id,
        action="USER_ROLE_MODIFIED",
        entity_type="user",
        entity_id=user.id,
        metadata={
            "email": user.email,
            "old_role": old_role,
            "new_role": payload.role,
        },
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return _serialize_user_detail(user)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppException("User not found.", status.HTTP_404_NOT_FOUND)
    if user.id == current_user.id:
        raise AppException("You cannot delete your own active administrator account.", status.HTTP_400_BAD_REQUEST)

    deleted_email = user.email
    deleted_name = user.full_name

    # Clean up dependent records safely
    db.query(Ticket).filter(Ticket.assigned_agent_id == user.id).update({"assigned_agent_id": None})
    db.query(TicketHistory).filter(TicketHistory.actor_id == user.id).update({"actor_id": None})
    db.query(TicketComment).filter(TicketComment.author_id == user.id).delete()
    db.query(TicketAttachment).filter(TicketAttachment.uploaded_by_id == user.id).delete()
    for t in db.query(Ticket).filter(Ticket.requester_id == user.id).all():
        db.delete(t)

    db.delete(user)

    record_audit_log(
        db=db,
        user_id=current_user.id,
        action="USER_DELETED",
        entity_type="user",
        entity_id=user_id,
        metadata={"email": deleted_email, "full_name": deleted_name},
        ip_address=get_client_ip(request),
    )
    db.commit()
    return {"success": True, "message": f"User '{deleted_name}' deleted."}


@router.post("/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    payload: AdminPasswordResetRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict:
    """Admin-assisted recovery after independent identity verification."""

    if user_id == current_user.id:
        raise AppException(
            "Administrators cannot reset their own password through this action.",
            status.HTTP_403_FORBIDDEN,
            "SELF_PASSWORD_RESET_FORBIDDEN",
        )

    try:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .with_for_update(of=User)
            .first()
        )

        if not user or not user.is_active:
            raise AppException(
                "Active user not found.",
                status.HTTP_404_NOT_FOUND,
                "USER_NOT_FOUND",
            )

        ticket = (
            db.query(Ticket)
            .filter(
                Ticket.id == payload.recovery_ticket_id,
                Ticket.requester_id == user.id,
            )
            .with_for_update(of=Ticket)
            .first()
        )

        if not ticket:
            raise AppException(
                "Matching recovery ticket not found.",
                status.HTTP_400_BAD_REQUEST,
                "INVALID_RECOVERY_TICKET",
            )

        category = db.query(TicketCategory).filter(
            TicketCategory.id == ticket.category_id,
            TicketCategory.slug == "access",
        ).first()

        team = db.query(SupportTeam).filter(
            SupportTeam.code == "IAM",
            SupportTeam.is_active.is_(True),
        ).first()

        if (
            not category
            or not team
            or ticket.subcategory != "Password Reset"
            or ticket.priority != "critical"
            or ticket.support_team_id != team.id
            or ticket.status in ("resolved", "closed", "transferred")
            or ticket.transferred_at is not None
        ):
            raise AppException(
                "Ticket is not an active Critical IAM password recovery request.",
                status.HTTP_400_BAD_REQUEST,
                "INVALID_RECOVERY_TICKET",
            )

        # Only accept tickets created by the dedicated public recovery service.
        system_created = db.query(TicketHistory.id).filter(
            TicketHistory.ticket_id == ticket.id,
            TicketHistory.actor_id.is_(None),
            TicketHistory.action == "CREATED",
            TicketHistory.description == (
                "System created an unverified password recovery request. "
                "Identity verification is required before any reset."
            ),
        ).first()

        if not system_created:
            raise AppException(
                "This ticket was not created by the password recovery service.",
                status.HTTP_400_BAD_REQUEST,
                "INVALID_RECOVERY_ORIGIN",
            )

        already_reset = db.query(TicketHistory.id).filter(
            TicketHistory.ticket_id == ticket.id,
            TicketHistory.action == "ADMIN_PASSWORD_RESET",
        ).first()

        if already_reset:
            raise AppException(
                "This recovery ticket has already been used for a reset.",
                status.HTTP_409_CONFLICT,
                "RECOVERY_TICKET_ALREADY_USED",
            )

        # Cryptographically secure, 32-character ASCII temporary password.
        temporary_password = secrets.token_urlsafe(24)
        now = datetime.now(timezone.utc)

        user.hashed_password = get_password_hash(temporary_password)
        user.must_change_password = True
        user.session_identity = str(uuid.uuid4())
        user.updated_at = now

        db.query(RefreshToken).filter(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked.is_(False),
        ).update(
            {
                "revoked": True,
                "revoked_at": now,
            },
            synchronize_session=False,
        )

        db.add(
            TicketHistory(
                ticket_id=ticket.id,
                actor_id=current_user.id,
                action="ADMIN_PASSWORD_RESET",
                description=(
                    "Administrator confirmed independent identity verification "
                    "and issued a temporary password. Mandatory password "
                    "change required at next sign-in."
                ),
                created_at=now,
            )
        )

        record_audit_log(
            db=db,
            user_id=current_user.id,
            action="ADMIN_PASSWORD_RESET",
            entity_type="user",
            entity_id=user.id,
            metadata={
                "recovery_ticket_id": ticket.id,
                "verification_method": payload.verification_method,
                "sessions_revoked": True,
                "must_change_password": True,
            },
            ip_address=request.client.host if request.client else None,
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    # Never cache the one-time password response.
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"

    return {
        "success": True,
        "message": (
            "Temporary password generated. Share it securely with the "
            "verified account holder. It will not be shown again."
        ),
        "temporary_password": temporary_password,
        "must_change_password": True,
    }
