"""Opaque request-scoped credentials for OpenHuman-owned MCP adapters."""

from __future__ import annotations

import base64
import json
from typing import Any

_PREFIX = "ohmcp1."


def pack_adapter_credential(kind: str, **values: str) -> str:
    payload = {"kind": kind, **values}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(
        b"="
    )
    return _PREFIX + encoded.decode()


def unpack_adapter_credential(value: str, expected_kind: str) -> dict[str, Any]:
    if not value.startswith(_PREFIX):
        raise ValueError("Invalid adapter credential")
    encoded = value.removeprefix(_PREFIX)
    encoded += "=" * (-len(encoded) % 4)
    payload = json.loads(base64.urlsafe_b64decode(encoded).decode())
    if not isinstance(payload, dict) or payload.get("kind") != expected_kind:
        raise ValueError("Adapter credential type mismatch")
    return payload
