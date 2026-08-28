from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.channel_assignments.models import ChannelAssignment
    from app.documents.models import Document
    from app.organizations.models import Organization
    from app.schedules.models import EmployeeSchedule


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'suspended')",
            name="ck_employees_status",
        ),
        CheckConstraint(
            "employee_type IS NULL OR employee_type IN ('legal-compliance', 'support', 'hr', 'general', 'sales')",
            name="ck_employees_employee_type",
        ),
        sa.Index(
            "ix_employees_org_id_employee_type",
            "org_id",
            "employee_type",
            unique=True,
            postgresql_where=sa.text("employee_type IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4
    )
    org_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    personality: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    specialization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employee_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    duties: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Bot tokens — encrypted at rest via AES-256-GCM
    discord_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    slack_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Slack workspace metadata
    slack_team_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slack_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slack_bot_user_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    mcp_connections: Mapped[list | None] = mapped_column(JSON, nullable=True)
    memory_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    escalation_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Cognee IDs — populated in Phase 4 fork
    cognee_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cognee_user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cognee_dataset_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cognee_dataset_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(
        String(50), default="inactive", server_default="inactive"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), default=None, nullable=True
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="employees"
    )
    channel_assignments: Mapped[list[ChannelAssignment]] = relationship(
        "ChannelAssignment",
        back_populates="employee",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    documents: Mapped[list[Document]] = relationship(
        "Document",
        back_populates="employee",
        passive_deletes=True,
    )
    schedules: Mapped[list[EmployeeSchedule]] = relationship(
        "EmployeeSchedule", cascade="all, delete-orphan", passive_deletes=True
    )
