from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.schemas.auth import DepartmentInfo, SupportTeamInfo, UserRoleInfo


class UserSummary(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    employee_id: Optional[str] = None
    job_title: Optional[str] = None
    role: str
    department_name: Optional[str] = None
    support_team_name: Optional[str] = None
    support_team_id: Optional[int] = None

    model_config = {"from_attributes": True}


class UserDetailResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    employee_id: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool
    role: str
    role_id: int
    department_id: Optional[int] = None
    support_team_id: Optional[int] = None
    role_info: Optional[UserRoleInfo] = None
    department: Optional[DepartmentInfo] = None
    support_team: Optional[SupportTeamInfo] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=150)
    password: str = Field(..., min_length=4, max_length=128)

    @field_validator("password")
    @classmethod
    def check_initial_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes.")
        return value
    employee_id: Optional[str] = Field(None, max_length=50)
    job_title: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=40)
    role: str = Field("employee", pattern="^(employee|agent|admin)$")
    department_id: Optional[int] = None
    support_team_id: Optional[int] = None
    department_name: Optional[str] = Field(None, min_length=2, max_length=120)
    support_team_name: Optional[str] = Field(None, min_length=2, max_length=120)
    is_active: bool = True

    @field_validator("full_name", "department_name", "support_team_name", mode="before")
    @classmethod
    def trim_names(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=150)
    email: Optional[EmailStr] = None
    employee_id: Optional[str] = Field(None, max_length=50)
    job_title: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=40)
    department_id: Optional[int] = None
    support_team_id: Optional[int] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=4, max_length=128)


class AdminPasswordResetRequest(BaseModel):
    recovery_ticket_id: int = Field(..., ge=1)
    identity_verified: Literal[True]
    verification_method: Literal[
        "in_person_id",
        "manager_callback",
        "hr_confirmation",
    ]


class UserRoleUpdateRequest(BaseModel):
    role: str = Field(..., pattern="^(employee|agent|admin)$")
    support_team_id: Optional[int] = None


class PaginatedUsersResponse(BaseModel):
    items: List[UserDetailResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SupportTeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    code: str = Field(..., min_length=2, max_length=30)
    description: Optional[str] = None
    specialization: Optional[str] = None


class DepartmentCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    code: str = Field(..., min_length=2, max_length=30)
    description: Optional[str] = None
    location: Optional[str] = None
