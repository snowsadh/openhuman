from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.employees.models import Employee
    from app.organizations.models import Organization


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded', 'processing', 'indexed', 'failed')",
            name="ck_documents_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    org_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Reserved for future per-document Cognee tracking (not currently populated).
    cognee_document_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    storage_backend: Mapped[str] = mapped_column(
        String(20), nullable=False, default="local", server_default="local"
    )
    status: Mapped[str] = mapped_column(
        String(50), default="uploaded", server_default="uploaded"
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="documents"
    )
    employee: Mapped[Employee | None] = relationship(
        "Employee", back_populates="documents"
    )

    @property
    def employee_name(self) -> str | None:
        """Agent/employee name from the joined relationship."""
        return self.employee.name if self.employee else None
