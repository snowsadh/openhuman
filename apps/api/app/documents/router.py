from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.activity.service import record_activity
from app.auth.models import User
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.documents.models import Document
from app.documents.schemas import DocumentResponse, DocumentsStatsResponse
from app.documents.service import (
    _backend_for,
    delete_document,
    get_document,
    get_documents_stats,
    list_documents,
    save_document,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    organization_id: UUID = Form(...),
    employee_id: UUID | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    """Upload a file and store its metadata. File saved to the configured storage backend."""
    doc = await save_document(db, organization_id, current_user.id, file, employee_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    # Re-fetch with eager-loaded employee to avoid MissingGreenlet on employee_name
    doc = await db.scalar(
        select(Document).options(joinedload(Document.employee)).where(Document.id == doc.id)
    )
    return DocumentResponse.model_validate(doc, from_attributes=True)


@router.get("", response_model=list[DocumentResponse])
async def list_org_documents(
    organization_id: UUID,
    employee_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DocumentResponse]:
    """List all documents for an organization, optionally filtered by employee."""
    docs = await list_documents(db, organization_id, current_user.id, employee_id)
    if docs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return [DocumentResponse.model_validate(d, from_attributes=True) for d in docs]


@router.get("/stats", response_model=DocumentsStatsResponse)
async def get_org_documents_stats(
    organization_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentsStatsResponse:
    """Get aggregate document statistics for an organization."""
    stats = await get_documents_stats(db, organization_id, current_user.id)
    if stats is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return stats


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document_route(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    doc = await get_document(db, doc_id, current_user.id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentResponse.model_validate(doc, from_attributes=True)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_route(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    doc = await get_document(db, doc_id, current_user.id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Record activity BEFORE delete (best-effort)
    try:
        await record_activity(
            db,
            doc.org_id,
            "document_upload",
            f"Deleted {doc.filename}",
            employee_id=doc.employee_id,
            platform="api",
            status="deleted",
            metadata={
                "filename": doc.filename,
                "content_type": doc.content_type,
                "size_bytes": doc.size_bytes,
            },
        )
    except Exception:
        pass

    deleted = await delete_document(db, doc_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")


@router.get("/{doc_id}/download", response_model=None)
async def download_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse | RedirectResponse:
    """Stream document content to the client, or redirect to a presigned S3 URL."""
    doc = await get_document(db, doc_id, current_user.id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if doc.storage_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on storage")

    backend = _backend_for(doc)

    # If the backend supports presigned URLs (S3), redirect for better performance
    presigned = backend.get_presigned_url(doc.storage_path)
    if presigned:
        return RedirectResponse(url=presigned)

    # Fallback: stream directly from the backend (avoids redundant DB queries)
    content_type = doc.content_type or "application/octet-stream"
    safe_name = doc.filename or "download"

    return StreamingResponse(
        backend.read_stream(doc.storage_path),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
        },
    )
