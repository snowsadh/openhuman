#!/usr/bin/env python3
"""
DEPRECATED — Slot-based Slack app provisioning has been removed.

The ``slack_app_slots`` table and ``SlackAppSlot`` model were dropped in the
fixed-bot migration.  Use fixed named bots instead:

1. Register a Slack app at https://api.slack.com/apps
2. Set the SLACK_BOT_<TYPE>_CLIENT_ID, SLACK_BOT_<TYPE>_CLIENT_SECRET, and
   SLACK_BOT_<TYPE>_APP_TOKEN env vars in .env
3. Set slack_identity_mode=fixed in .env
4. Restart the API — the fixed bot registry picks up the env vars automatically.

See: app/gateway/fixed_bots.py for the registry.
"""
from __future__ import annotations

import sys


def main() -> None:
    print(__doc__, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
