from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.employees.models import Employee


class AgentJob(Base):
    """A background job enqueued by an agent tool for async execution.

    Heavy tools (document analysis, knowledge-base search, etc.) insert a row
    here and return immediately.  Background workers pick up pending jobs,
    execute the real work, and post results back to Slack / Discord.
    """

    __tablename__ = "agent_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'pending','running','awaiting_approval','succeeded','failed','cancelled'"
            ")",
            name="ck_agent_jobs_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4
    )
    employee_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="slack | discord"
    )
    channel_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    thread_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        comment="Stable conversation id: {platform}:{employee_id}:{channel_id}:{root_ts}",
    )
    job_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    payload: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Tool arguments"
    )
    schedule_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("employee_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    delivery_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    user_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Original user message text"
    )
    status: Mapped[str] = mapped_column(
        String(50), default="pending", server_default="pending", index=True
    )
    result_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Worker-written result"
    )
    progress: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Worker-updated progress blob"
    )
    error: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    employee: Mapped[Employee] = relationship(
        "Employee",
        primaryjoin="AgentJob.employee_id == Employee.id",
        uselist=False,
        viewonly=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AgentJob(id={self.id!r}, job_type={self.job_type!r}, "
            f"status={self.status!r}, thread_key={self.thread_key!r})>"
        )
