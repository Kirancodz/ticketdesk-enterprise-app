import uuid
import ipaddress
import socket
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from threading import Lock
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.core.exceptions import AppException
from app.core.logging_config import logger
from app.core.security import (
    create_access_token,
    create_refresh_token_value,
    get_password_hash,
    hash_token,
    verify_password,
)
from app.middleware.rate_limit import get_client_ip, login_rate_limiter
from app.models.user import RefreshToken, User
from app.schemas.auth import (
    ForgotPasswordTicketRequest,
    ChangePasswordRequest,
    AdminProfileUpdateRequest,
    AuthUserResponse,
    DepartmentInfo,
    ForgotPasswordOTPRequest,
    ForgotPasswordOTPResponse,
    ForgotPasswordResetRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    SupportTeamInfo,
    TokenResponse,
    UserRoleInfo,
)
from app.services.audit_service import record_audit_log
from app.services.sla_service import ensure_utc

from app.middleware.rate_limit import password_reset_request_limiter
from app.services.password_recovery_service import create_password_recovery_ticket

router = APIRouter(prefix="/auth", tags=["Authentication"])

# In-memory OTP store: key = user_id -> {otp_hash, expires_at, phone_digits, attempts}
_otp_store: dict[int, dict] = {}
_otp_lock = Lock()
OTP_EXPIRY_SECONDS = 600


def _normalize_phone_digits(phone: str | None) -> str:
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def _mask_phone(phone: str) -> str:
    digits = _normalize_phone_digits(phone)
    if len(digits) <= 4:
        return phone
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


def _find_user_for_otp(db: Session, email: str | None, phone: str) -> User:
    input_digits = _normalize_phone_digits(phone)
    if len(input_digits) < 6:
        raise AppException(
            message="Please enter a valid phone number (at least 6 digits).",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_PHONE_NUMBER",
        )

    user: User | None = None
    if email and email.strip():
        user = (
            db.query(User)
            .filter(func.lower(User.email) == email.lower().strip())
            .first()
        )
        if not user:
            raise AppException(
                message="No active user account found with that email address.",
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="USER_NOT_FOUND",
            )
        user_digits = _normalize_phone_digits(user.phone)
        # Allow matching either full digits or last 10 digits, or if user has no phone saved yet, bind it
        if user_digits:
            if not (
                user_digits == input_digits
                or user_digits[-10:] == input_digits[-10:]
            ):
                raise AppException(
                    message="The phone number entered does not match the phone number registered on this account.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    error_code="PHONE_MISMATCH",
                )
        else:
            user.phone = phone.strip()
            db.commit()
    else:
        # Lookup user directly by phone digits
        active_users = db.query(User).filter(User.is_active == True).all()  # noqa: E712
        for candidate in active_users:
            cand_digits = _normalize_phone_digits(candidate.phone)
            if cand_digits and (
                cand_digits == input_digits
                or cand_digits[-10:] == input_digits[-10:]
            ):
                user = candidate
                break
        if not user:
            raise AppException(
                message="No active user account found matching that phone number. Try providing your corporate email as well.",
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="PHONE_NOT_FOUND",
            )

    if not user.is_active:
        raise AppException(
            message="This user account is deactivated. Contact an administrator.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="ACCOUNT_DEACTIVATED",
        )
    return user


def build_auth_user_response(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        employee_id=user.employee_id,
        job_title=user.job_title,
        phone=user.phone,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        role=user.role,
        role_info=UserRoleInfo.model_validate(user.role_rel) if user.role_rel else None,
        department=DepartmentInfo.model_validate(user.department_rel) if user.department_rel else None,
        support_team=SupportTeamInfo.model_validate(user.support_team_rel) if user.support_team_rel else None,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    ip = get_client_ip(request)
    rate_key = f"{ip}:{payload.email.lower()}"
    login_rate_limiter.check(rate_key)

    user = (
        db.query(User)
        .filter(func.lower(User.email) == payload.email.lower().strip())
        .first()
    )
    if not user or not verify_password(payload.password, user.hashed_password):
        login_rate_limiter.record_failure(rate_key)
        raise AppException(
            message="Invalid email address or password.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="INVALID_CREDENTIALS",
        )

    if not user.is_active:
        raise AppException(
            message="Your account has been deactivated. Please contact an IT Administrator.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="ACCOUNT_DEACTIVATED",
        )

    login_rate_limiter.reset(rate_key)
    now = datetime.now(timezone.utc)
    user.last_login_at = now

    access_token = create_access_token(subject=user.id, role=user.role, session_identity=user.session_identity)
    raw_refresh = create_refresh_token_value()
    refresh_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        session_identity=user.session_identity,
        role_at_issue=user.role,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        revoked=False,
        user_agent=request.headers.get("User-Agent", "")[:255],
        ip_address=ip,
        created_at=now,
    )
    db.add(refresh_record)

    record_audit_log(
        db=db,
        user_id=user.id,
        action="USER_LOGIN",
        entity_type="user",
        entity_id=user.id,
        metadata={"email": user.email, "role": user.role},
        ip_address=ip,
        user_agent=request.headers.get("User-Agent", "")[:255],
    )
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=build_auth_user_response(user),
    )









@router.post(
    "/forgot-password/request-ticket",
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_recovery_ticket(
    payload: ForgotPasswordTicketRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Accept an unverified password recovery request."""

    email = str(payload.email).strip().lower()

    # Trust forwarded IP only from our Docker frontend service.
    # Nginx overwrites X-Forwarded-For with $remote_addr.
    peer_ip = request.client.host if request.client else ""
    client_ip = peer_ip or "unknown"

    try:
        trusted_proxy_ips = {
            address[4][0]
            for address in socket.getaddrinfo(
                "frontend", None, type=socket.SOCK_STREAM
            )
        }
    except OSError:
        trusted_proxy_ips = set()

    if peer_ip in trusted_proxy_ips:
        forwarded = request.headers.get("x-forwarded-for", "").strip()
        if forwarded and "," not in forwarded:
            try:
                client_ip = str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass

    password_reset_request_limiter.check_and_record(
        client_ip=client_ip,
        identifier=email,
    )

    matched = create_password_recovery_ticket(
        db=db,
        email=email,
        employee_id=payload.employee_id,
        reason=payload.reason,
        client_ip=client_ip,
    )

    if not matched:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="Incorrect Email ID or Employee ID.",
        )

    return {
        "message": "Request submitted successfully!"
    }


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Change password and invalidate every existing login session."""

    if not verify_password(payload.current_password, current_user.hashed_password):
        raise AppException(
            message="Current password is incorrect.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INCORRECT_CURRENT_PASSWORD",
        )

    if payload.new_password != payload.confirm_password:
        raise AppException(
            message="New password and confirmation do not match.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="PASSWORD_MISMATCH",
        )

    if verify_password(payload.new_password, current_user.hashed_password):
        raise AppException(
            message="New password must be different from the current password.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="PASSWORD_REUSE",
        )

    now = datetime.now(timezone.utc)

    current_user.hashed_password = get_password_hash(payload.new_password)
    current_user.must_change_password = False
    current_user.session_identity = str(uuid.uuid4())
    current_user.updated_at = now

    db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.id,
        RefreshToken.revoked == False,
    ).update(
        {"revoked": True, "revoked_at": now},
        synchronize_session=False,
    )

    record_audit_log(
        db=db,
        user_id=current_user.id,
        action="PASSWORD_CHANGED",
        entity_type="user",
        entity_id=current_user.id,
        metadata={"method": "authenticated_password_change"},
        ip_address=get_client_ip(request),
    )

    db.commit()

    return {
        "success": True,
        "message": "Password changed successfully. Please log in again.",
        "logout_required": True,
    }

@router.post("/refresh", response_model=TokenResponse)
def refresh_access_token(
    payload: RefreshTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    token_hash = hash_token(payload.refresh_token)
    record = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    now = datetime.now(timezone.utc)
    if not record or record.revoked:
        raise AppException(
            message="Refresh token is invalid or has been revoked.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="INVALID_REFRESH_TOKEN",
        )

    exp = ensure_utc(record.expires_at)
    if not exp or exp < now:
        record.revoked = True
        record.revoked_at = now
        db.commit()
        raise AppException(
            message="Refresh token has expired. Please sign in again.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="REFRESH_TOKEN_EXPIRED",
        )

    user = db.query(User).filter(User.id == record.user_id, User.is_active == True).first()  # noqa: E712
    if not user:
        raise AppException(
            message="User account is no longer active.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="USER_INACTIVE",
        )

    if not user.session_identity or record.session_identity != user.session_identity or record.role_at_issue != user.role:
        raise AppException("The account or role changed. Please sign in explicitly.", status.HTTP_401_UNAUTHORIZED, "SESSION_IDENTITY_CHANGED")

    record.revoked = True
    record.revoked_at = now

    new_refresh_raw = create_refresh_token_value()
    new_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_refresh_raw),
        session_identity=user.session_identity,
        role_at_issue=user.role,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        revoked=False,
        user_agent=request.headers.get("User-Agent", "")[:255],
        ip_address=get_client_ip(request),
        created_at=now,
    )
    db.add(new_record)
    db.commit()

    access_token = create_access_token(subject=user.id, role=user.role, session_identity=user.session_identity)
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_raw,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=build_auth_user_response(user),
    )


@router.post("/logout")
def logout(
    payload: LogoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc)
    if payload.refresh_token:
        token_hash = hash_token(payload.refresh_token)
        record = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.token_hash == token_hash,
                RefreshToken.user_id == current_user.id,
            )
            .first()
        )
        if record and not record.revoked:
            record.revoked = True
            record.revoked_at = now
    else:
        db.query(RefreshToken).filter(
            RefreshToken.user_id == current_user.id,
            RefreshToken.revoked == False,  # noqa: E712
        ).update({"revoked": True, "revoked_at": now})

    record_audit_log(
        db=db,
        user_id=current_user.id,
        action="USER_LOGOUT",
        entity_type="user",
        entity_id=current_user.id,
        metadata={"email": current_user.email},
    )
    db.commit()
    return {"success": True, "message": "Logged out and invalidated refresh token."}


@router.get("/me", response_model=AuthUserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> AuthUserResponse:
    return build_auth_user_response(current_user)


@router.put("/me", response_model=AuthUserResponse)
def update_admin_profile(
    payload: AdminProfileUpdateRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AuthUserResponse:
    """Allow Administrators to edit and save their own profile attributes directly."""
    email_clean = payload.email.lower().strip()
    if email_clean != current_user.email.lower():
        dup = db.query(User).filter(func.lower(User.email) == email_clean, User.id != current_user.id).first()
        if dup:
            raise AppException("Another user already uses this email address.", status.HTTP_409_CONFLICT)
        current_user.email = email_clean

    if payload.employee_id is not None:
        emp_clean = payload.employee_id.strip() or None
        if emp_clean and emp_clean != current_user.employee_id:
            dup_emp = db.query(User).filter(User.employee_id == emp_clean, User.id != current_user.id).first()
            if dup_emp:
                raise AppException("Employee ID is already assigned to another user.", status.HTTP_409_CONFLICT)
        current_user.employee_id = emp_clean

    current_user.full_name = payload.full_name.strip()
    current_user.job_title = payload.job_title.strip() if payload.job_title else None
    current_user.phone = payload.phone.strip() if payload.phone else None

    if payload.department_id is not None:
        current_user.department_id = payload.department_id if payload.department_id > 0 else None
    if payload.support_team_id is not None:
        current_user.support_team_id = payload.support_team_id if payload.support_team_id > 0 else None
    if payload.new_password is not None:
        raise AppException(
            message="Use the Change Password page to update your password.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="PASSWORD_CHANGE_ACTION_REQUIRED",
        )

    current_user.updated_at = datetime.now(timezone.utc)

    record_audit_log(
        db=db,
        user_id=current_user.id,
        action="ADMIN_PROFILE_UPDATED",
        entity_type="user",
        entity_id=current_user.id,
        metadata={
            "full_name": current_user.full_name,
            "email": current_user.email,
            "employee_id": current_user.employee_id,
            "phone": current_user.phone,
        },
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(current_user)
    return build_auth_user_response(current_user)
