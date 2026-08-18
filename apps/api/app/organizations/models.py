from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.auth.models import User
    from app.documents.models import Document
    from app.employees.models import Employee


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    owner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_it_does: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Cognee IDs — populated in Phase 4 fork, nullable until then
    cognee_tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cognee_tenant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cognee_system_user_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    cognee_system_user_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    cognee_dataset_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cognee_dataset_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    owner: Mapped[User] = relationship("User", back_populates="organizations")
    employees: Mapped[list[Employee]] = relationship(
        "Employee",
        back_populates="organization",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    documents: Mapped[list[Document]] = relationship(
        "Document",
        back_populates="organization",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
