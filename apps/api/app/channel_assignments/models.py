from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.employees.models import Employee


class ChannelAssignment(Base):
    __tablename__ = "channel_assignments"
    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "platform",
            "channel_id",
            name="uq_channel_assignments_employee_platform_channel",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    employee_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    employee: Mapped[Employee] = relationship(
        "Employee", back_populates="channel_assignments"
    )
