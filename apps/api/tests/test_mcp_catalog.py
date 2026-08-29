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


def test_zop_runtime_exposes_mcp_marketplace_routes() -> None:
    source = (Path(__file__).parents[1] / "app" / "zop_main.py").read_text()

    assert "app.include_router(mcp_router)" in source
    assert "app.include_router(mcp_oauth_router)" in source
