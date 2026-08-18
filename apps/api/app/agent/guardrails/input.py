import re

from app.core.security_utils.threat_patterns import scan_for_threats


def check_input(content: str, guardrail_config: dict | None = None) -> tuple[bool, str | None]:
    """Check the user input against safety/guardrail policies.

    Returns:
        tuple[bool, str | None]: (is_blocked, reason)
    """
    if len(content) > 4000:
        return True, "Message is too long (limit is 4000 characters)."

    config = guardrail_config or {}

    # Threat pattern scanning (prompt injection, exfiltration, C2, etc.)
    threat_scope = config.get("threat_scan_scope", "context")
    if threat_scope not in ("all", "context", "strict"):
        threat_scope = "all"
    findings = scan_for_threats(content, scope=threat_scope)
    if findings:
        pid = findings[0]
        if pid.startswith("invisible_unicode_"):
            codepoint = pid.replace("invisible_unicode_", "")
            return (
                True,
                f"Input contains invisible unicode character {codepoint} (possible injection).",
            )
        return True, f"Potential threat detected: '{pid}'."

    # Basic PII check (email, phone, etc.) if enabled
    if config.get("block_pii", False):
        email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        phone_pattern = r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"
        if re.search(email_pattern, content) or re.search(phone_pattern, content):
            return True, "Personally Identifiable Information (PII) is not allowed."

    return False, None
