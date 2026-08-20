from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ActivityEvent(Base):
    """Explicitly recorded activity event — the write-side of the activity feed.

    Events are recorded at each touchpoint (agent conversations, memory ops,
    MCP connections, org changes, Slack OAuth, channel assignments) and read
    back via a UNION with agent_jobs / documents / employees in the feed query.
    """

    __tablename__ = "activity_events"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    org_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON string for expandable detail"
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    employee_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Denormalized for query speed"
    )
    platform: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="slack | discord | api"
    )
    status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="succeeded | failed | pending | ..."
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, comment="Extra structured payload"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_activity_events_org_occurred",
            "org_id",
            "occurred_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ActivityEvent(id={self.id!r}, event_type={self.event_type!r}, "
            f"summary={self.summary[:60]!r})>"
        )
