"""Fixed Slack bot registry — one named bot per employee type.

Instead of a dynamic pool of ``SlackAppSlot`` rows, the system ships with a
small set of **fixed** Slack app identities.  Each employee type maps to
exactly one bot name/persona that is shared across all customer organisations.

Credentials are loaded from environment variables at startup via
``app.core.config.settings``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class FixedBot:
    """Immutable descriptor for a pre-registered Slack bot identity."""

    name: str
    role: str
    employee_type: str
    description: str

    # ── Credentials (populated from env) ──────────────────────────────
    client_id: str
    client_secret: str
    app_token: str

    @property
    def is_configured(self) -> bool:
        """Return ``True`` if all three credentials are present."""
        return bool(self.client_id and self.client_secret and self.app_token)


def _build_registry() -> dict[str, FixedBot]:
    """Build the registry from settings.  Called once at import time."""
    return {
        "hr": FixedBot(
            name="Alison",
            role="HR Specialist",
            employee_type="hr",
            description="Manages onboarding, benefits, policies, and employee questions",
            client_id=settings.slack_bot_hr_client_id,
            client_secret=settings.slack_bot_hr_client_secret,
            app_token=settings.slack_bot_hr_app_token,
        ),
        "support": FixedBot(
            name="Alex",
            role="Customer Support Specialist",
            employee_type="support",
            description="Handles customer inquiries, support tickets, and troubleshooting",
            client_id=settings.slack_bot_support_client_id,
            client_secret=settings.slack_bot_support_client_secret,
            app_token=settings.slack_bot_support_app_token,
        ),
        "sales": FixedBot(
            name="Marcus",
            role="Sales Representative",
            employee_type="sales",
            description="Qualifies leads, researches prospects, and tracks pipeline metrics",
            client_id=settings.slack_bot_sales_client_id,
            client_secret=settings.slack_bot_sales_client_secret,
            app_token=settings.slack_bot_sales_app_token,
        ),
        "general": FixedBot(
            name="Jordan",
            role="General Assistant",
            employee_type="general",
            description="Versatile assistant for research, calculations, and general tasks",
            client_id=settings.slack_bot_general_client_id,
            client_secret=settings.slack_bot_general_client_secret,
            app_token=settings.slack_bot_general_app_token,
        ),
        "legal-compliance": FixedBot(
            name="Taylor",
            role="Legal & Compliance Officer",
            employee_type="legal-compliance",
            description="Reviews contracts, policies, and regulatory documents",
            client_id=settings.slack_bot_legal_client_id,
            client_secret=settings.slack_bot_legal_client_secret,
            app_token=settings.slack_bot_legal_app_token,
        ),
    }


# Module-level singleton — rebuilt only on process restart.
FIXED_BOTS: dict[str, FixedBot] = _build_registry()


def get_fixed_bot(employee_type: str) -> FixedBot | None:
    """Return the fixed bot for *employee_type*, or ``None`` if unknown."""
    return FIXED_BOTS.get(employee_type)


def get_configured_bots() -> list[FixedBot]:
    """Return only bots whose credentials are fully configured."""
    return [bot for bot in FIXED_BOTS.values() if bot.is_configured]


def list_all_bots() -> list[FixedBot]:
    """Return all fixed bots regardless of configuration status."""
    return list(FIXED_BOTS.values())
