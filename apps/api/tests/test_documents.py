"""Tests for document service — Phase 1 behavior.

Covers: employee dataset routing (1a), all-format path-based ingest (1b),
delete limitation note (1c), status progression (Gap 11).
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure all model modules are imported before SQLAlchemy mapper configuration
import app.auth.models  # noqa: F401
import app.channel_assignments.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.employees.models  # noqa: F401
import app.organizations.models  # noqa: F401
import app.agent.tools.mcp.models  # noqa: F401


def _make_org(org_id: UUID | None = None, **overrides) -> MagicMock:
    org = MagicMock()
    org.id = org_id or uuid4()
    org.name = "Test Org"
    org.cognee_tenant_id = "tenant-123"
    org.cognee_tenant_name = "Test Org"
    org.cognee_system_user_id = "sys-user-456"
    org.cognee_system_user_name = "system+tenant-123@openhuman.internal"
    org.cognee_dataset_id = "ds-789"
    org.cognee_dataset_name = "company-tenant-123"
    for k, v in overrides.items():
        setattr(org, k, v)
    return org


def _make_emp(emp_id: UUID | None = None, **overrides) -> MagicMock:
    emp = MagicMock()
    emp.id = emp_id or uuid4()
    emp.name = "Test Employee"
    emp.org_id = uuid4()
    emp.cognee_user_id = "ai-user-111"
    emp.cognee_user_name = "ai-test+tenant@openhuman.internal"
    emp.cognee_dataset_id = "ds-222"
    emp.cognee_dataset_name = f"employee-{emp.id}"
    for k, v in overrides.items():
        setattr(emp, k, v)
    return emp


class TestSaveDocumentPhase1:
    """Phase 1 behavior: employee routing, all-format ingest, status progression."""

    @pytest.mark.anyio
    async def test_save_without_employee_id_ingests_to_org_dataset(self):
        """Documents without employee_id go to org Cognee dataset."""
        from app.documents.service import save_document

        org = _make_org()
        file = MagicMock()
        file.filename = "test.txt"
        file.content_type = "text/plain"
        file.read = AsyncMock(return_value=b"Hello world")

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=org)

        with patch("app.documents.service.get_storage_backend") as mock_bf:
            mock_bf.return_value.save = AsyncMock(return_value="org-123/test.txt")

            with patch("app.documents.service.remember") as mock_remember:
                result = await save_document(mock_db, org.id, uuid4(), file)

        assert result is not None
        assert mock_remember.called
        _, dataset_name, user_id = mock_remember.call_args[0][:3]
        assert dataset_name == org.cognee_dataset_name
        assert user_id == org.cognee_system_user_id

    @pytest.mark.anyio
    async def test_save_with_employee_id_ingests_to_employee_dataset(self):
        """Phase 1a: employee-tagged docs go to employee Cognee dataset."""
        from app.documents.service import save_document

        org = _make_org()
        emp = _make_emp()
        emp.org_id = org.id

        file = MagicMock()
        file.filename = "emp_doc.txt"
        file.content_type = "text/plain"
        file.read = AsyncMock(return_value=b"Employee-specific content")

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=org)
        mock_db.get = AsyncMock(return_value=emp)

        with patch("app.documents.service.get_storage_backend") as mock_bf:
            mock_bf.return_value.save = AsyncMock(return_value="org-123/emp_doc.txt")

            with patch("app.documents.service.remember") as mock_remember:
                result = await save_document(mock_db, org.id, uuid4(), file, employee_id=emp.id)

        assert result is not None
        assert result.employee_id == emp.id
        assert mock_remember.called
        _, dataset_name, user_id = mock_remember.call_args[0][:3]
        assert dataset_name == emp.cognee_dataset_name
        assert user_id == emp.cognee_user_id

    @pytest.mark.anyio
    async def test_employee_no_cognee_falls_back_to_org(self):
        """When employee has no Cognee provisioning, fall back to org dataset with warning."""
        from app.documents.service import save_document

        org = _make_org()
        emp = _make_emp(
            cognee_user_id=None,
            cognee_dataset_name=None,
            cognee_dataset_id=None,
        )
        emp.org_id = org.id

        file = MagicMock()
        file.filename = "emp_doc.txt"
        file.content_type = "text/plain"
        file.read = AsyncMock(return_value=b"content")

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=org)
        mock_db.get = AsyncMock(return_value=emp)

        with patch("app.documents.service.get_storage_backend") as mock_bf:
            mock_bf.return_value.save = AsyncMock(return_value="org-123/emp_doc.txt")

            with patch("app.documents.service.remember") as mock_remember:
                with patch.object(logging.getLogger("app.documents.service"), "warning") as mock_warn:
                    result = await save_document(mock_db, org.id, uuid4(), file, employee_id=emp.id)

        assert result is not None
        assert mock_remember.called
        _, dataset_name, _ = mock_remember.call_args[0][:3]
        assert dataset_name == org.cognee_dataset_name  # fell back to org
        # Warning should mention the employee
        mock_warn.assert_called_once()
        assert "incomplete cognee provisioning" in mock_warn.call_args[0][0].lower()

    @pytest.mark.anyio
    async def test_all_file_formats_ingested_via_bucket_path(self):
        """Phase 1b: all files (including PDFs) go to Cognee via bucket path."""
        from app.documents.service import save_document

        org = _make_org()
        file = MagicMock()
        file.filename = "report.pdf"
        file.content_type = "application/pdf"
        file.read = AsyncMock(return_value=b"%PDF-1.4 fake pdf content")

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=org)

        with patch("app.documents.service.get_storage_backend") as mock_bf:
            mock_bf.return_value.save = AsyncMock(return_value="org-123/report.pdf")

            with patch("app.documents.service.remember") as mock_remember:
                result = await save_document(mock_db, org.id, uuid4(), file)

        assert result is not None
        assert mock_remember.called
        # Verify the bucket storage path was passed (not a temp file, not decoded text)
        data_arg = mock_remember.call_args[0][0]
        assert data_arg == "org-123/report.pdf"  # direct bucket path

    @pytest.mark.anyio
    async def test_status_progresses_to_indexed_on_success(self):
        """Phase 1b/5d: status set to 'indexed' after successful Cognee ingest."""
        from app.documents.service import save_document

        org = _make_org()
        file = MagicMock()
        file.filename = "doc.txt"
        file.content_type = "text/plain"
        file.read = AsyncMock(return_value=b"content")

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=org)

        with patch("app.documents.service.get_storage_backend") as mock_bf:
            mock_bf.return_value.save = AsyncMock(return_value="org-123/doc.txt")

            with patch("app.documents.service.remember"):
                result = await save_document(mock_db, org.id, uuid4(), file)

        assert result is not None
        assert result.status == "indexed"

    @pytest.mark.anyio
    async def test_status_set_to_failed_on_cognee_error(self):
        """Phase 5d: status set to 'failed' when Cognee ingest errors."""
        from app.documents.service import save_document

        org = _make_org()
        file = MagicMock()
        file.filename = "doc.txt"
        file.content_type = "text/plain"
        file.read = AsyncMock(return_value=b"content")

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=org)

        with patch("app.documents.service.get_storage_backend") as mock_bf:
            mock_bf.return_value.save = AsyncMock(return_value="org-123/doc.txt")

            with patch("app.documents.service.remember", side_effect=RuntimeError("Cognee down")):
                result = await save_document(mock_db, org.id, uuid4(), file)

        assert result is not None
        assert result.status == "failed"
        # Document is still saved even though Cognee failed

    @pytest.mark.anyio
    async def test_org_not_found_returns_none(self):
        from app.documents.service import save_document

        file = MagicMock()
        file.filename = "doc.txt"
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=None)

        result = await save_document(mock_db, uuid4(), uuid4(), file)
        assert result is None

    @pytest.mark.anyio
    async def test_cognee_skipped_when_org_not_provisioned(self):
        """Gap 10 fix: warning logged when Cognee not provisioned."""
        from app.documents.service import save_document

        org = _make_org(cognee_dataset_name=None, cognee_system_user_id=None)
        file = MagicMock()
        file.filename = "doc.txt"
        file.content_type = "text/plain"
        file.read = AsyncMock(return_value=b"content")

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=org)

        with patch("app.documents.service.get_storage_backend") as mock_bf:
            mock_bf.return_value.save = AsyncMock(return_value="org-123/doc.txt")

            with patch("app.documents.service.remember") as mock_remember:
                with patch.object(logging.getLogger("app.documents.service"), "warning") as mock_warn:
                    result = await save_document(mock_db, org.id, uuid4(), file)

        assert result is not None
        assert not mock_remember.called
        mock_warn.assert_called_once()
        assert "cognee not provisioned" in mock_warn.call_args[0][0].lower()

    @pytest.mark.anyio
    async def test_storage_path_passed_directly_to_cognee(self):
        """Cognee receives the bucket storage_path (or S3 URL), not a temp file copy."""
        from app.documents.service import save_document

        org = _make_org()
        file = MagicMock()
        file.filename = "doc.txt"
        file.content_type = "text/plain"
        file.read = AsyncMock(return_value=b"Hello world")

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=org)

        with patch("app.documents.service.get_storage_backend") as mock_bf:
            mock_bf.return_value.save = AsyncMock(return_value="org-123/doc.txt")

            with patch("app.documents.service.remember") as mock_remember:
                result = await save_document(mock_db, org.id, uuid4(), file)

        assert result is not None
        assert mock_remember.called
        # First positional arg should be the storage path (not a temp path)
        data_arg = mock_remember.call_args[0][0]
        assert data_arg == "org-123/doc.txt"


    @pytest.mark.anyio
    async def test_s3_storage_uses_s3_url_for_cognee(self):
        """When storage_backend is 's3', Cognee receives s3://bucket/key URL."""
        from app.documents.service import save_document

        org = _make_org()
        file = MagicMock()
        file.filename = "report.pdf"
        file.content_type = "application/pdf"
        file.read = AsyncMock(return_value=b"%PDF-1.4 content")

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=org)

        with patch("app.documents.service.settings") as mock_settings:
            mock_settings.storage_backend = "s3"
            mock_settings.s3_bucket_name = "my-bucket"

            with patch("app.documents.service.get_storage_backend") as mock_bf:
                mock_bf.return_value.save = AsyncMock(return_value="org-123/abc123_report.pdf")

                with patch("app.documents.service.remember") as mock_remember:
                    result = await save_document(mock_db, org.id, uuid4(), file)

        assert result is not None
        assert mock_remember.called
        data_arg = mock_remember.call_args[0][0]
        assert data_arg == "s3://my-bucket/org-123/abc123_report.pdf"


class TestDeleteDocumentPhase1:
    """Phase 1c: delete removes from storage + DB, Cognee forget is not attempted."""

    @pytest.mark.anyio
    async def test_delete_removes_from_storage_and_db(self):
        from app.documents.service import delete_document

        org = _make_org()
        doc_mock = MagicMock()
        doc_mock.id = uuid4()
        doc_mock.org_id = org.id
        doc_mock.storage_path = "org-123/test.txt"
        doc_mock.storage_backend = "local"

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(side_effect=[doc_mock, org])

        with patch("app.documents.service.get_local_backend") as mock_local:
            mock_backend = MagicMock()
            mock_backend.delete = AsyncMock()
            mock_local.return_value = mock_backend

            result = await delete_document(mock_db, doc_mock.id, uuid4())

        assert result is True
        mock_backend.delete.assert_awaited_once_with("org-123/test.txt")
        mock_db.delete.assert_called_once_with(doc_mock)

    @pytest.mark.anyio
    async def test_delete_doc_not_found_returns_false(self):
        from app.documents.service import delete_document

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=None)

        result = await delete_document(mock_db, uuid4(), uuid4())
        assert result is False
