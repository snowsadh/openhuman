"""Baseline tests for organization service — pins current behavior before Phase 3 changes.

These tests verify the CURRENT state of create_org, update_org, delete_org
so we can confirm existing paths don't break when we add website_url and
ScrapeGraphAI integration in Phase 3.
"""

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


class TestCreateOrgCurrentBehavior:
    """Pin current create_org behavior — no website_url, Cognee best-effort."""

    @pytest.mark.anyio
    async def test_create_org_without_website_url(self):
        """Org creation without website_url works (current state — no URL field yet)."""
        from app.organizations.service import create_org
        from app.organizations.schemas import CreateOrganizationRequest

        data = CreateOrganizationRequest(
            name="Test Org",
            description="A test org",
            what_it_does="Testing",
        )
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Mock Cognee provisioning to avoid real Cognee calls
        with patch("app.organizations.service.get_or_create_admin") as mock_admin, \
             patch("app.organizations.service.create_tenant") as mock_tenant, \
             patch("app.organizations.service.create_system_user") as mock_user, \
             patch("app.organizations.service.add_user_to_tenant") as mock_add, \
             patch("app.organizations.service.create_dataset") as mock_ds, \
             patch("app.organizations.service.grant_tenant_read") as mock_grant, \
             patch("app.organizations.service.remember") as mock_remember:

            mock_admin.return_value = {"id": "admin-1", "email": "admin@test"}
            mock_tenant.return_value = {"id": "tenant-1", "name": "Test Org"}
            mock_user.return_value = {"id": "sys-1", "email": "sys@test"}
            mock_ds.return_value = {"id": "ds-1", "name": "company-tenant-1"}

            result = await create_org(mock_db, uuid4(), data)

        assert result is not None
        assert result.name == "Test Org"
        assert result.description == "A test org"
        assert result.what_it_does == "Testing"
        assert result.website_url is None  # Phase 3a: field exists, not set
        # Cognee IDs should be set after successful provisioning
        assert result.cognee_tenant_id == "tenant-1"

    @pytest.mark.anyio
    async def test_create_org_cognee_failure_non_blocking(self):
        """When Cognee provisioning fails, org is still created successfully."""
        from app.organizations.service import create_org
        from app.organizations.schemas import CreateOrganizationRequest

        data = CreateOrganizationRequest(name="Test Org")
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch("app.organizations.service.get_or_create_admin", side_effect=RuntimeError("Cognee down")):
            result = await create_org(mock_db, uuid4(), data)

        assert result is not None
        assert result.name == "Test Org"
        # Cognee fields should remain None since provisioning failed
        assert result.cognee_tenant_id is None


class TestUpdateOrgCurrentBehavior:
    """Pin current update_org behavior — no website_url, no re-scrape."""

    @pytest.mark.anyio
    async def test_update_org_name(self):
        from app.organizations.service import update_org
        from app.organizations.schemas import UpdateOrganizationRequest

        org = MagicMock()
        org.name = "Old Name"
        org.description = "Old desc"

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=org)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        data = UpdateOrganizationRequest(name="New Name")
        result = await update_org(mock_db, uuid4(), uuid4(), data)

        assert result is not None
        assert result.name == "New Name"

    @pytest.mark.anyio
    async def test_update_org_not_found_returns_none(self):
        from app.organizations.service import update_org
        from app.organizations.schemas import UpdateOrganizationRequest

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=None)

        data = UpdateOrganizationRequest(name="New Name")
        result = await update_org(mock_db, uuid4(), uuid4(), data)
        assert result is None


class TestDeleteOrgCurrentBehavior:
    """Pin current delete_org behavior — Cognee cleanup, cascade."""

    @pytest.mark.anyio
    async def test_delete_org_cleans_up_cognee(self):
        from app.organizations.service import delete_org

        org = MagicMock()
        org.id = uuid4()
        org.name = "Test Org"
        org.cognee_dataset_name = "company-tenant-1"
        org.employees = []  # No employees to iterate

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=org)
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch("app.organizations.service.forget_dataset") as mock_forget:
            result = await delete_org(mock_db, org.id, uuid4())

        assert result is True
        mock_forget.assert_called_once_with(org.cognee_dataset_name)
        mock_db.delete.assert_called_once_with(org)

    @pytest.mark.anyio
    async def test_delete_org_cleans_up_employee_datasets_too(self):
        from app.organizations.service import delete_org

        emp1 = MagicMock()
        emp1.cognee_dataset_name = "employee-emp1"
        emp2 = MagicMock()
        emp2.cognee_dataset_name = "employee-emp2"

        org = MagicMock()
        org.id = uuid4()
        org.cognee_dataset_name = "company-tenant-1"
        org.employees = [emp1, emp2]

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=org)
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch("app.organizations.service.forget_dataset") as mock_forget:
            result = await delete_org(mock_db, org.id, uuid4())

        assert result is True
        assert mock_forget.call_count == 3  # 2 employees + 1 org

    @pytest.mark.anyio
    async def test_delete_org_not_found_returns_false(self):
        from app.organizations.service import delete_org

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar = AsyncMock(return_value=None)

        result = await delete_org(mock_db, uuid4(), uuid4())
        assert result is False
