from app.agent.tools.mcp.connectors.registry import REGISTRY
from app.agent.tools.mcp.connectors.spec import ConnectorSpec

# Individual connector specs — re-exported from REGISTRY for backward compat
CANVA_CONNECTOR = REGISTRY.get("canva")
GAMMA_CONNECTOR = REGISTRY.get("gamma")
GITHUB_CONNECTOR = REGISTRY.get("github")
GMAIL_CONNECTOR = REGISTRY.get("gmail")
N8N_CONNECTOR = REGISTRY.get("n8n")
NOTION_CONNECTOR = REGISTRY.get("notion")
PITCHDECK_CONNECTOR = REGISTRY.get("pitchdeck")
VERCEL_CONNECTOR = REGISTRY.get("vercel")
VISUALIZATION_CONNECTOR = REGISTRY.get("visualization")
WEB_SEARCH_CONNECTOR = REGISTRY.get("web_search")

__all__ = [
    "REGISTRY",
    "ConnectorSpec",
    "CANVA_CONNECTOR",
    "GITHUB_CONNECTOR",
    "GMAIL_CONNECTOR",
    "NOTION_CONNECTOR",
    "PITCHDECK_CONNECTOR",
    "VERCEL_CONNECTOR",
    "VISUALIZATION_CONNECTOR",
    "WEB_SEARCH_CONNECTOR",
    "GAMMA_CONNECTOR",
    "N8N_CONNECTOR",
]
