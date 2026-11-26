from typing import Callable, Sequence
import jwt
from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.security import decode_access_token
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials or not credentials.credentials:
        raise AppException(
            message="Authentication credentials were not provided.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="NOT_AUTHENTICATED",
        )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        if payload.get("type") != "access":
            raise AppException(
                message="Invalid token type.",
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="INVALID_TOKEN_TYPE",
            )
        user_id = payload.get("sub")
        if user_id is None:
            raise AppException(
                message="Token payload missing subject.",
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="INVALID_TOKEN",
            )
    except jwt.ExpiredSignatureError:
        raise AppException(
            message="Access token has expired. Please refresh your token or sign in again.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="TOKEN_EXPIRED",
        )
    except jwt.InvalidTokenError:
        raise AppException(
            message="Invalid or malformed authentication token.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="INVALID_TOKEN",
        )

    try:
        subject_id = int(user_id)
    except (TypeError, ValueError):
        raise AppException("Invalid token subject.", status.HTTP_401_UNAUTHORIZED, "INVALID_TOKEN")
    user = db.query(User).filter(User.id == subject_id).first()
    if not user:
        raise AppException(
            message="Authenticated user account no longer exists.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="USER_NOT_FOUND",
        )
    if not user.session_identity or payload.get("sid") != user.session_identity or payload.get("role") != user.role:
        raise AppException("The account or role changed. Please sign in explicitly.", status.HTTP_401_UNAUTHORIZED, "SESSION_IDENTITY_CHANGED")
    if not user.is_active:
        raise AppException(
            message="Your user account has been deactivated. Contact an administrator.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="ACCOUNT_DEACTIVATED",
        )

    # Temporary-password users must complete password change first.
    allowed_paths = {
        "/api/v1/auth/change-password",
        "/api/v1/auth/me",
        "/api/v1/auth/logout",
        "/auth/change-password",
        "/auth/me",
        "/auth/logout",
    }

    current_path = request.url.path.rstrip("/")

    if user.must_change_password and current_path not in allowed_paths:
        raise AppException(
            message="You must change your temporary password before continuing.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="PASSWORD_CHANGE_REQUIRED",
        )

    return user


def require_roles(allowed_roles: Sequence[str]) -> Callable[[User], User]:
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise AppException(
                message=f"Access denied. Required role: {', '.join(allowed_roles)}.",
                status_code=status.HTTP_403_FORBIDDEN,
                error_code="INSUFFICIENT_PERMISSIONS",
            )
        return current_user

    return role_checker


require_admin = require_roles(["admin"])
require_agent_or_admin = require_roles(["agent", "admin"])
