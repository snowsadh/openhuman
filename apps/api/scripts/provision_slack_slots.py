#!/usr/bin/env python3
"""
DEPRECATED — Slot-based Slack app provisioning has been removed.

The ``slack_app_slots`` table, ``app.gateway.models`` module, and
``app.gateway.slack_app_provisioning`` module were removed in the fixed-bot
migration.  Use fixed named bots instead:

1. Register 5 Slack apps at https://api.slack.com/apps (one per employee type):
   - HR (Alison)
   - Support (Alex)
   - Sales (Marcus)
   - General (Jordan)
   - Legal-Compliance (Taylor)
2. Set the corresponding env vars in .env:
   SLACK_BOT_HR_CLIENT_ID, SLACK_BOT_HR_CLIENT_SECRET, SLACK_BOT_HR_APP_TOKEN
   SLACK_BOT_SUPPORT_CLIENT_ID, ...
   SLACK_BOT_SALES_CLIENT_ID, ...
   SLACK_BOT_GENERAL_CLIENT_ID, ...
   SLACK_BOT_LEGAL_CLIENT_ID, ...
3. Set slack_identity_mode=fixed in .env
4. No DB provisioning needed — credentials are read from env at startup.

See: app/gateway/fixed_bots.py for the registry.
"""
from __future__ import annotations

import sys


def main() -> None:
    print(__doc__, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
