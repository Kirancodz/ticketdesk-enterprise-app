from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    session_identity = Column(String(36), default=lambda: str(uuid4()), nullable=True, unique=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(150), nullable=False, index=True)
    employee_id = Column(String(50), unique=True, nullable=True, index=True)
    job_title = Column(String(120), nullable=True)
    phone = Column(String(40), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    role_id = Column(Integer, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    support_team_id = Column(Integer, ForeignKey("support_teams.id", ondelete="SET NULL"), nullable=True, index=True)

    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    role_rel = relationship("Role", back_populates="users", lazy="joined")
    department_rel = relationship("Department", back_populates="users", lazy="joined")
    support_team_rel = relationship("SupportTeam", back_populates="members", lazy="joined")

    requested_tickets = relationship(
        "Ticket",
        foreign_keys="Ticket.requester_id",
        back_populates="requester",
    )
    assigned_tickets = relationship(
        "Ticket",
        foreign_keys="Ticket.assigned_agent_id",
        back_populates="assigned_agent",
    )
    comments = relationship("TicketComment", back_populates="author")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

    @property
    def role(self) -> str:
        return self.role_rel.name if self.role_rel else "employee"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_identity = Column(String(36), nullable=True)
    role_at_issue = Column(String(50), nullable=True)
    token_hash = Column(String(128), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    user_agent = Column(String(255), nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="refresh_tokens")
