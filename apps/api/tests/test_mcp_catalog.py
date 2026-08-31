"""Regression coverage for the marketplace catalog exposed on Zop."""

from pathlib import Path

from app.agent.tools.mcp.catalog import list_catalog, register_catalog_connectors
from app.agent.tools.mcp.connectors.registry import REGISTRY


def test_catalog_includes_manifest_and_marketplace_connectors() -> None:
    entries = list_catalog()
    by_slug = {entry.slug: entry for entry in entries}

    assert len(entries) == 41
    assert len(by_slug) == len(entries)
    assert {
        "gmail",
        "github",
        "notion",
        "pitchdeck",
        "visualization",
        "web_search",
        "slack",
        "jira",
        "postgres",
        "salesforce",
    } <= by_slug.keys()
    assert by_slug["github"].category == "Development"
    assert by_slug["notion"].category == "Productivity"


def test_every_catalog_connector_can_be_registered() -> None:
    register_catalog_connectors()

    assert {entry.slug for entry in list_catalog()} <= REGISTRY.keys()


def test_first_ten_connectors_have_real_installable_definitions() -> None:
    by_slug = {entry.slug: entry for entry in list_catalog()}
    first_ten = {
        "slack",
        "gmail",
        "google-calendar",
        "github",
        "notion",
        "hubspot",
        "zendesk",
        "web_search",
        "n8n",
        "canva",
    }

    assert first_ten <= REGISTRY.keys()
    assert all(by_slug[slug].is_installable for slug in first_ten)
    assert by_slug["google-calendar"].url == (
        "https://calendarmcp.googleapis.com/mcp/v1"
    )
    assert by_slug["hubspot"].url == "https://mcp.hubspot.com"
    assert by_slug["zendesk"].catalog_state == "beta"


def test_unverified_marketplace_entries_are_not_installable() -> None:
    by_slug = {entry.slug: entry for entry in list_catalog()}

    assert by_slug["postgres"].catalog_state == "unavailable"
    assert by_slug["postgres"].is_installable is False


def test_connection_verification_is_required_before_agent_tool_resolution() -> None:
    api_root = Path(__file__).parents[1] / "app"
    router_source = (api_root / "mcp" / "router.py").read_text()
    agent_source = (api_root / "agent" / "router.py").read_text()

    assert '"/employees/{emp_id}/mcp-connections/{slug}/verify"' in router_source
    assert "mint_intent_token" in router_source
    assert 'McpConnection.verification_status == "verified"' in agent_source


def test_zop_runtime_exposes_mcp_marketplace_routes() -> None:
    source = (Path(__file__).parents[1] / "app" / "zop_main.py").read_text()

    assert "app.include_router(mcp_router)" in source
    assert "app.include_router(mcp_oauth_router)" in source
