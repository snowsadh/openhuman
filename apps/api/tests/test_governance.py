from __future__ import annotations

import json
from pathlib import Path

from app.governance.service import redact_parameters


def test_redaction_removes_credentials_and_message_payloads() -> None:
    source = {
        "start_date": "2026-09-01",
        "amount": 2500,
        "access_token": "must-not-leak",
        "message": "private customer message",
        "nested": {"password": "must-not-leak", "record_id": "ticket-42"},
    }

    assert redact_parameters(source) == {
        "start_date": "2026-09-01",
        "amount": 2500,
        "access_token": "[redacted]",
        "message": "[redacted]",
        "nested": {"password": "[redacted]", "record_id": "ticket-42"},
    }


def test_production_policy_is_deny_by_default_with_all_three_decisions() -> None:
    path = (
        Path(__file__).parents[3]
        / "deploy"
        / "armoriq"
        / "policies"
        / "openhuman-production.json"
    )
    policy = json.loads(path.read_text())
    effects = {statement["effect"] for statement in policy["statements"]}
    principals = {
        statement["principal"]["id"] for statement in policy["statements"]
    }

    assert policy["schemaVersion"] == "armor.policy.v1"
    assert policy["defaults"]["decision"] == "deny"
    assert effects == {"permit", "require_approval", "forbid"}
    assert principals == {
            "openhuman-jordan",
        "openhuman-alison",
        "openhuman-marcus",
        "openhuman-alex",
        "openhuman-taylor",
    }
