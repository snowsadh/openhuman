"""Load ConnectorSpec objects from YAML manifests in the manifests/ directory."""

from __future__ import annotations

import os
import logging
from pathlib import Path

import yaml

from app.agent.tools.mcp.connectors.spec import ConnectorSpec

logger = logging.getLogger(__name__)

MANIFESTS_DIR = Path(__file__).parent / "manifests"


def _resolve_path(value: str, manifest_path: Path) -> str:
    """Resolve ${MANIFEST_DIR} placeholders in string values."""
    manifest_dir = str(manifest_path.parent)
    return value.replace("${MANIFEST_DIR}", manifest_dir)


def _resolve_in(value: str | list[str], manifest_path: Path) -> str | list[str]:
    """Recursively resolve placeholders in strings or lists of strings."""
    if isinstance(value, str):
        return _resolve_path(value, manifest_path)
    if isinstance(value, list):
        return [_resolve_path(v, manifest_path) if isinstance(v, str) else v for v in value]
    return value


def _load_single_manifest(path: Path) -> ConnectorSpec | None:
    """Load a single YAML manifest and return a ConnectorSpec."""
    if path.suffix not in (".yaml", ".yml"):
        return None

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, dict):
        logger.warning("Empty or invalid manifest: %s", path)
        return None

    slug = data.get("name", path.stem)
    transport = data.get("transport", {})
    auth = data.get("auth", {})
    tools = data.get("tools", {})
    settings = data.get("settings", {})

    transport_type = transport.get("type", "streamable_http")
    base_url = _resolve_in(transport.get("url"), path)
    command = _resolve_in(transport.get("command"), path)
    args = _resolve_in(transport.get("args", []), path)

    auth_type = auth.get("type", "none")

    spec = ConnectorSpec(
        slug=slug,
        name=data.get("name", slug),
        description=data.get("description", ""),
        base_url=base_url if transport_type != "stdio" else None,
        transport=transport_type,
        command=command if transport_type == "stdio" else None,
        args=args if transport_type == "stdio" else [],
        auth_type=auth_type,
        alternative_auth_types=auth.get("alternative_types", []),
        requires_custom_server_url=settings.get("requires_custom_server_url", False),
        authorize_url=auth.get("authorize_url"),
        token_url=auth.get("token_url"),
        default_scopes=auth.get("scopes", []),
        docs_url=data.get("source", ""),
        default_tool_allow=tools.get("default_allow"),
        default_tool_deny=tools.get("default_deny", []),
        request_timeout_seconds=settings.get("request_timeout_seconds", 30.0),
        rate_limit_per_minute=settings.get("rate_limit_per_minute", 60),
        token_auth_method=auth.get("token_auth_method", "form"),
        supports_token_refresh=auth.get("supports_refresh", False),
        requires_manual_approval=settings.get("requires_manual_approval", False),
    )
    return spec


def load_manifests() -> dict[str, ConnectorSpec]:
    """Load all YAML manifests from the manifests/ directory.

    Returns a dict mapping slug -> ConnectorSpec.
    """
    if not MANIFESTS_DIR.is_dir():
        logger.warning("Manifests directory not found: %s", MANIFESTS_DIR)
        return {}

    result: dict[str, ConnectorSpec] = {}
    for path in sorted(MANIFESTS_DIR.iterdir()):
        if path.suffix not in (".yaml", ".yml"):
            continue
        spec = _load_single_manifest(path)
        if spec is not None:
            result[spec.slug] = spec
            logger.debug("Loaded manifest: %s (%s)", spec.slug, path.name)

    if result:
        logger.info("Loaded %d MCP connector manifests", len(result))
    return result
