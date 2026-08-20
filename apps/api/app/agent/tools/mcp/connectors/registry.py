"""Connector registry — populated from YAML manifests.

Each connector is described by a YAML manifest in the ``manifests/``
directory, which is loaded at import time into a ``ConnectorSpec``.
No Python code change is needed to add a new connector — just drop a
YAML file into ``manifests/``.
"""

from app.agent.tools.mcp.connectors.spec import ConnectorSpec
from app.agent.tools.mcp.manifest_loader import load_manifests

# Re-export for backwards compatibility
__all__ = ["REGISTRY", "ConnectorSpec"]

# ---------------------------------------------------------------------------
# Registry — loaded from YAML manifests.
# ---------------------------------------------------------------------------

REGISTRY: dict[str, ConnectorSpec] = load_manifests()
