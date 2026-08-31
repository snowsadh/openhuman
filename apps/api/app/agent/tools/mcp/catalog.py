"""MCP catalog — manifest-based MCP server registry.

Each catalog entry is a ``CatalogEntry`` that can be installed by any org.
When installed, the system auto-generates a ``ConnectorSpec`` on-the-fly and
registers it into the global ``REGISTRY`` — no Python code change required.

The catalog ships built-in entries covering the full marketplace. Third-party
entries can be added by placing YAML manifests in ``manifests/``.

Design
------
* Built-in entries are defined as ``CatalogEntry`` instances in ``_BUILTIN_MANIFESTS``.
  They are registered at import time as ``ConnectorSpec`` objects with
  ``from_catalog=True`` so the system knows they came from the catalog.

* Custom entries can be added via YAML files in ``manifests/`` subdirectory,
  following the same format as Hermes-Agent's ``optional-mcps/<name>/manifest.yaml``.

* When a user installs a catalog entry, the credential is stored in the
  ``mcp_connections`` DB table (same as hardcoded connectors). The ConnectorSpec
  is already in REGISTRY, so no runtime registration is needed.

* When a user uninstalls, the ConnectorSpec stays in REGISTRY (it's shared
  across orgs). The connection row is revoked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.agent.tools.mcp.connectors.spec import ConnectorSpec

logger = logging.getLogger(__name__)


@dataclass
class CatalogEntry:
    """A single catalog entry — enough info to wire into the marketplace UI
    and auto-generate a ``ConnectorSpec``."""

    slug: str
    name: str
    description: str
    category: str
    url: str
    auth_type: str  # "none" | "api_key" | "pat_bearer" | "oauth2"
    docs_url: str = ""
    icon: str = ""
    requires_custom_server_url: bool = False
    request_timeout_seconds: float = 30.0
    supports_token_refresh: bool = False
    requires_manual_approval: bool = False
    catalog_state: str = "unavailable"
    is_installable: bool = False


# ---------------------------------------------------------------------------
# Built-in manifests — covers the full marketplace
# ---------------------------------------------------------------------------

_BUILTIN_MANIFESTS: dict[str, CatalogEntry] = {}

# Slugs that ship as built-in manifests — listed for reference but NOT
# registered by the catalog system. The manifest loader already puts them
# into REGISTRY at import time.
_MANIFEST_SLUGS = frozenset(
    {
        "gmail",
        "github",
        "notion",
        "vercel",
        "n8n",
        "gamma",
        "canva",
        "pitchdeck",
        "visualization",
        "web_search",
        "slack",
        "google-calendar",
        "hubspot",
        "zendesk",
    }
)


def _register_manifest(
    slug: str,
    name: str,
    description: str,
    category: str,
    url: str,
    auth_type: str,
    **kwargs: Any,
) -> None:
    """Register a built-in catalog entry."""
    _BUILTIN_MANIFESTS[slug] = CatalogEntry(
        slug=slug,
        name=name,
        description=description,
        category=category,
        url=url,
        auth_type=auth_type,
        **kwargs,
    )


# ── Communication ──────────────────────────────────────────────────────────
# Manifest-backed connectors must also appear in the marketplace. Their
# transport/auth details still come from YAML; these entries add the display
# metadata consumed by the catalog API.
_register_manifest(
    "gmail",
    "Gmail",
    "Search threads, read messages, create drafts, and manage Gmail labels.",
    "Communication",
    "https://gmailmcp.googleapis.com/mcp/v1",
    "oauth2",
    docs_url="https://developers.google.com/workspace/gmail/api/guides/configure-mcp-server",
    catalog_state="verified",
    is_installable=True,
)

_register_manifest(
    "github",
    "GitHub",
    "Search code, manage repositories, create issues, and work with pull requests.",
    "Development",
    "https://api.githubcopilot.com/mcp/",
    "pat_bearer",
    docs_url="https://docs.github.com/en/enterprise-cloud@latest/copilot/developing-with-copilot/mcp/using-github-copilot-mcp-server",
    catalog_state="verified",
    is_installable=True,
)

_register_manifest(
    "notion",
    "Notion",
    "Search, read, create, and update Notion pages and databases.",
    "Productivity",
    "https://mcp.notion.com/mcp",
    "oauth2",
    docs_url="https://developers.notion.com/guides/mcp/get-started-with-mcp",
    catalog_state="verified",
    is_installable=True,
)

_register_manifest(
    "vercel",
    "Vercel",
    "Manage projects, deployments, domains, logs, and environment variables.",
    "Development",
    "https://mcp.vercel.com",
    "oauth2",
    docs_url="https://vercel.com/docs/rest-api",
)

_register_manifest(
    "n8n",
    "n8n",
    "Search workflows, trigger runs, and build or edit workflows on an n8n instance.",
    "Development",
    "",
    "pat_bearer",
    docs_url="https://docs.n8n.io/build/ways-of-building-workflows/connect-to-n8n-mcp-server/",
    requires_custom_server_url=True,
    request_timeout_seconds=60.0,
    catalog_state="verified",
    is_installable=True,
)

_register_manifest(
    "gamma",
    "Gamma",
    "Generate and manage presentations, documents, and web pages.",
    "Productivity",
    "https://mcp.gamma.app/mcp",
    "oauth2",
    docs_url="https://gamma.app/docs",
)

_register_manifest(
    "canva",
    "Canva",
    "Generate, edit, and export designs, presentations, PDFs, and images.",
    "Productivity",
    "https://mcp.canva.com/mcp",
    "oauth2",
    docs_url="https://www.canva.dev/docs/mcp/",
    catalog_state="verified",
    is_installable=True,
)

_register_manifest(
    "pitchdeck",
    "Pitch Deck Generator",
    "Generate styled PowerPoint pitch decks locally without an API key.",
    "Productivity",
    "",
    "none",
)

_register_manifest(
    "visualization",
    "Visualization",
    "Create charts, plots, heatmaps, and network diagrams locally.",
    "AI & Search",
    "",
    "none",
)

_register_manifest(
    "web_search",
    "Web Search",
    "Search the public web for current information without an API key.",
    "AI & Search",
    "https://rival-search-mcp.fly.dev/mcp",
    "none",
    docs_url="https://github.com/taskiq/RivalSearchMCP",
    catalog_state="beta",
    is_installable=True,
)

_register_manifest(
    "slack",
    "Slack Channel Manager",
    "Search messages, read channel history, post messages, and manage "
    "workspace users and channels.",
    "Communication",
    "https://mcp.slack.com/mcp",
    "oauth2",
    docs_url="https://api.slack.com/mcp",
    catalog_state="verified",
    is_installable=True,
)

_register_manifest(
    "discord",
    "Discord Webhook Dispatch",
    "Send messages, read channel history, manage guild members, and automate server moderation.",
    "Communication",
    "https://mcp.discord.com/mcp",
    "oauth2",
    docs_url="https://discord.com/developers/docs",
)

_register_manifest(
    "twilio",
    "Twilio SMS & Messaging",
    "Send SMS, query message logs, manage phone numbers, and automate text-based notifications.",
    "Communication",
    "https://mcp.twilio.com/mcp",
    "api_key",
    docs_url="https://www.twilio.com/docs",
)

_register_manifest(
    "zoom",
    "Zoom Meetings Scheduler",
    "Create meetings, list upcoming events, manage participants, and pull attendance transcripts.",
    "Communication",
    "https://mcp.zoom.us/mcp",
    "oauth2",
    docs_url="https://developers.zoom.us/docs",
)

_register_manifest(
    "google-calendar",
    "Google Calendar Invites",
    "Read events, create invites, update schedules, and sync availability across calendar views.",
    "Communication",
    "https://calendarmcp.googleapis.com/mcp/v1",
    "oauth2",
    docs_url="https://developers.google.com/workspace/calendar/api/guides/configure-mcp-server",
    catalog_state="verified",
    is_installable=True,
)

_register_manifest(
    "medium",
    "Medium Publisher",
    "Create and publish stories, manage publications, and analyze post performance metrics.",
    "Communication",
    "https://mcp.medium.com/mcp",
    "oauth2",
    docs_url="https://medium.com/mcp/docs",
)

# ── Development ────────────────────────────────────────────────────────────
_register_manifest(
    "gitlab",
    "GitLab Pipelines",
    "Browse repositories, create merge requests, trigger CI pipelines, and manage project members.",
    "Development",
    "https://mcp.gitlab.com/mcp",
    "pat_bearer",
    docs_url="https://docs.gitlab.com/ee/api/",
)

_register_manifest(
    "jira",
    "Jira Workflows",
    "Create and search issues, manage sprints, query project boards, and "
    "transition workflow statuses.",
    "Development",
    "https://mcp.atlassian.com/jira/mcp",
    "oauth2",
    docs_url="https://developer.atlassian.com/cloud/jira",
)

_register_manifest(
    "linear",
    "Linear Agile Tracker",
    "Create and assign issues, manage projects and cycles, query team roadmaps, "
    "and update issue states.",
    "Development",
    "https://mcp.linear.app/mcp",
    "oauth2",
    docs_url="https://developers.linear.app",
)

_register_manifest(
    "trello",
    "Trello Agile Boards",
    "Manage boards, lists, and cards; assign members, set due dates, and track project progress.",
    "Development",
    "https://mcp.trello.com/mcp",
    "oauth2",
    docs_url="https://developer.atlassian.com/cloud/trello",
)

_register_manifest(
    "clickup",
    "ClickUp Tasks",
    "Create tasks, manage lists and folders, track time, and automate team workflows.",
    "Development",
    "https://mcp.clickup.com/mcp",
    "oauth2",
    docs_url="https://clickup.com/api",
)

_register_manifest(
    "figma",
    "Figma Artboard Inspector",
    "Read design files, inspect layers and components, extract styles, and manage team libraries.",
    "Development",
    "https://mcp.figma.com/mcp",
    "pat_bearer",
    docs_url="https://www.figma.com/developers",
)

_register_manifest(
    "docker",
    "Docker Engine Daemon",
    "List containers, inspect images, manage volumes, and monitor engine resource usage.",
    "Development",
    "https://mcp.docker.com/mcp",
    "api_key",
    docs_url="https://docs.docker.com/engine/api/",
)

_register_manifest(
    "redis",
    "Redis Server Memory",
    "Execute commands, inspect keys, monitor memory usage, and manage cache clusters.",
    "Development",
    "https://mcp.redis.com/mcp",
    "pat_bearer",
    docs_url="https://redis.io/docs/",
)

# ── Data & DBs ─────────────────────────────────────────────────────────────
_register_manifest(
    "postgres",
    "PostgreSQL Database Inspect",
    "Query tables, inspect schemas, run EXPLAIN plans, and manage database migrations.",
    "Data & DBs",
    "https://mcp.postgres.com/mcp",
    "pat_bearer",
    docs_url="https://www.postgresql.org/docs/",
)

_register_manifest(
    "snowflake",
    "Snowflake Warehouse SQL",
    "Run SQL queries, list schemas, manage warehouses, and monitor query performance.",
    "Data & DBs",
    "https://mcp.snowflake.com/mcp",
    "pat_bearer",
    docs_url="https://docs.snowflake.com/en/developer-guide",
)

_register_manifest(
    "airtable",
    "Airtable Custom Bases",
    "Query records, manage bases and tables, update fields, and automate data workflows.",
    "Data & DBs",
    "https://mcp.airtable.com/mcp",
    "oauth2",
    docs_url="https://airtable.com/developers",
)

_register_manifest(
    "elasticsearch",
    "Elasticsearch Index",
    "Search indices, manage mappings, analyze query performance, and monitor cluster health.",
    "Data & DBs",
    "https://mcp.elastic.co/mcp",
    "api_key",
    docs_url="https://www.elastic.co/guide",
)

_register_manifest(
    "firebase",
    "Firebase Cloud Auth",
    "Manage users, verify tokens, configure auth providers, and monitor authentication logs.",
    "Data & DBs",
    "https://mcp.firebase.com/mcp",
    "oauth2",
    docs_url="https://firebase.google.com/docs",
)

_register_manifest(
    "aws-s3",
    "AWS S3 Cloud Buckets",
    "List buckets, upload/download objects, manage access policies, and monitor storage usage.",
    "Data & DBs",
    "https://mcp.aws.com/s3/mcp",
    "api_key",
    docs_url="https://docs.aws.amazon.com/s3/",
)

# ── AI & Search ────────────────────────────────────────────────────────────
_register_manifest(
    "brave-search",
    "Brave Search Engine",
    "Perform web searches, retrieve news results, fetch local business data, "
    "and aggregate answer boxes.",
    "AI & Search",
    "https://mcp.brave.com/search/mcp",
    "api_key",
    docs_url="https://brave.com/search/api/",
)

_register_manifest(
    "huggingface",
    "HuggingFace Model Index",
    "Query model catalog, read model cards, list datasets, and trigger inference requests.",
    "AI & Search",
    "https://mcp.huggingface.co/mcp",
    "api_key",
    docs_url="https://huggingface.co/docs",
)

_register_manifest(
    "exa-search",
    "Exa Neural Search",
    "Perform semantic searches, query content indexes, retrieve web embeddings, "
    "and analyze link graphs.",
    "AI & Search",
    "https://mcp.exa.ai/mcp",
    "api_key",
    docs_url="https://docs.exa.ai",
)

_register_manifest(
    "youtube",
    "YouTube Data API",
    "Search videos, get channel stats, list playlists, and retrieve transcript metadata.",
    "AI & Search",
    "https://mcp.youtube.com/mcp",
    "api_key",
    docs_url="https://developers.google.com/youtube",
)

_register_manifest(
    "wikipedia",
    "Wikipedia Encyclopedia",
    "Search articles, get page summaries, list categories, and retrieve cross-language links.",
    "AI & Search",
    "https://mcp.wikipedia.org/mcp",
    "none",
    docs_url="https://www.mediawiki.org/wiki/API",
)

_register_manifest(
    "google-maps",
    "Google Maps Navigation",
    "Geocode addresses, search places, calculate routes, and retrieve real-time traffic data.",
    "AI & Search",
    "https://mcp.googleapis.com/maps/mcp",
    "api_key",
    docs_url="https://developers.google.com/maps",
)

# ── Productivity / CRM / Sales ─────────────────────────────────────────────
_register_manifest(
    "salesforce",
    "Salesforce CRM Leads",
    "Query accounts and contacts, manage opportunities, run SOQL queries, and "
    "automate pipeline tasks.",
    "Productivity",
    "https://mcp.salesforce.com/mcp",
    "oauth2",
    docs_url="https://developer.salesforce.com",
)

_register_manifest(
    "hubspot",
    "HubSpot Contacts Tracker",
    "Manage contacts and deals, track email engagement, query pipelines, and update CRM records.",
    "Productivity",
    "https://mcp.hubspot.com",
    "oauth2",
    docs_url="https://developers.hubspot.com/docs/apps/developer-platform/build-apps/integrate-with-the-remote-hubspot-mcp-server",
    catalog_state="verified",
    is_installable=True,
)

_register_manifest(
    "zendesk",
    "Zendesk Help Center",
    "Manage tickets, search knowledge base articles, view user profiles, and "
    "update support workflows.",
    "Productivity",
    "",
    "api_key",
    docs_url="https://developer.zendesk.com/api-reference/",
    requires_custom_server_url=True,
    catalog_state="beta",
    is_installable=True,
)

_register_manifest(
    "shopify",
    "Shopify Storefront",
    "Manage products and variants, process orders, update inventory, and query customer data.",
    "Productivity",
    "https://mcp.shopify.com/mcp",
    "oauth2",
    docs_url="https://shopify.dev/docs/api",
)

_register_manifest(
    "stripe",
    "Stripe Billing Dashboard",
    "Process payments, manage customers, create invoices, and monitor subscription lifecycle.",
    "Productivity",
    "https://mcp.stripe.com/mcp",
    "api_key",
    docs_url="https://stripe.com/docs/api",
)

# ---------------------------------------------------------------------------
# Catalog access API
# ---------------------------------------------------------------------------


def list_catalog() -> list[CatalogEntry]:
    """Return all catalog entries sorted by slug."""
    return sorted(_BUILTIN_MANIFESTS.values(), key=lambda e: e.slug)


def get_catalog_entry(slug: str) -> CatalogEntry | None:
    """Look up a catalog entry by slug."""
    return _BUILTIN_MANIFESTS.get(slug)


def is_hardcoded(slug: str) -> bool:
    """Return True if *slug* ships as a built-in manifest (not a catalog-only entry)."""
    return slug in _MANIFEST_SLUGS


# ---------------------------------------------------------------------------
# ConnectorSpec generation from catalog entries
# ---------------------------------------------------------------------------

_CATALOG_AUTH_MAP: dict[str, str] = {
    "none": "none",
    "api_key": "api_key_header",
    "pat": "pat_bearer",
    "pat_bearer": "pat_bearer",
    "oauth2": "oauth2",
}


def build_connector_spec(entry: CatalogEntry) -> ConnectorSpec:
    """Auto-generate a ``ConnectorSpec`` from a ``CatalogEntry``."""
    auth_type = _CATALOG_AUTH_MAP.get(entry.auth_type, "none")
    return ConnectorSpec(
        slug=entry.slug,
        name=entry.name,
        description=entry.description,
        base_url=entry.url,
        transport="streamable_http" if entry.url.startswith("http") else "stdio",
        auth_type=auth_type,  # type: ignore[arg-type]
        docs_url=entry.docs_url,
        requires_custom_server_url=entry.requires_custom_server_url,
        request_timeout_seconds=entry.request_timeout_seconds,
        supports_token_refresh=entry.supports_token_refresh,
        requires_manual_approval=entry.requires_manual_approval,
    )


# ---------------------------------------------------------------------------
# Auto-registration into the global REGISTRY
#
# All catalog entries whose slug is NOT already in the hardcoded REGISTRY
# get registered automatically. This makes the marketplace servers "just
# work" — the backend has a ConnectorSpec for every marketplace entry.
# ---------------------------------------------------------------------------

# NOTE: This import is deferred so catalog.py can be imported standalone
# without triggering the full REGISTRY import chain.


def register_catalog_connectors() -> int:
    """Register all catalog entries into ``REGISTRY``.

    Returns the number of newly registered entries (excludes manifest-based
    connectors and already-registered slugs).

    Call this once at startup (e.g., in the FastAPI lifespan or app init).
    """
    # Deferred import to avoid circular dependency at module level
    from app.agent.tools.mcp.connectors.registry import REGISTRY

    count = 0
    for entry in list_catalog():
        if entry.slug in REGISTRY:
            continue
        spec = build_connector_spec(entry)
        REGISTRY[entry.slug] = spec
        count += 1

    if count:
        logger.info("Registered %d catalog-derived MCP connectors in REGISTRY", count)
    return count
