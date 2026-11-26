from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=4, max_length=128)




class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=4, max_length=128)
    new_password: str = Field(..., min_length=12, max_length=128)
    confirm_password: str = Field(..., min_length=12, max_length=128)

    @field_validator("new_password", "confirm_password")
    @classmethod
    def check_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes.")
        return value

class ForgotPasswordTicketRequest(BaseModel):
    email: EmailStr
    employee_id: str = Field(..., min_length=1, max_length=50)
    reason: str = Field(..., min_length=10, max_length=500)

    @field_validator("employee_id")
    @classmethod
    def clean_employee_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Employee ID is required.")
        return cleaned

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 10:
            raise ValueError("Please provide a valid reset reason.")
        return cleaned


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


class AdminProfileUpdateRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    employee_id: Optional[str] = Field(None, max_length=50)
    job_title: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=40)
    department_id: Optional[int] = None
    support_team_id: Optional[int] = None
    new_password: Optional[str] = Field(None, min_length=4, max_length=128)

    @field_validator("new_password")
    @classmethod
    def check_profile_password_bytes(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes.")
        return value


class ForgotPasswordOTPRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone: str = Field(..., min_length=6, max_length=40)


class ForgotPasswordOTPResponse(BaseModel):
    success: bool
    message: str
    masked_phone: str
    email: str
    expires_in_seconds: int
    dev_otp_code: Optional[str] = None


class ForgotPasswordResetRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone: str = Field(..., min_length=6, max_length=40)
    otp_code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=4, max_length=128)


class UserRoleInfo(BaseModel):
    id: int
    name: str
    display_name: str

    model_config = {"from_attributes": True}


class DepartmentInfo(BaseModel):
    id: int
    name: str
    code: str
    location: Optional[str] = None

    model_config = {"from_attributes": True}


class SupportTeamInfo(BaseModel):
    id: int
    name: str
    code: str
    specialization: Optional[str] = None

    model_config = {"from_attributes": True}


class AuthUserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    employee_id: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool
    must_change_password: bool = False
    role: str
    role_info: Optional[UserRoleInfo] = None
    department: Optional[DepartmentInfo] = None
    support_team: Optional[SupportTeamInfo] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUserResponse
