"""Security checks for MCP connector configurations.

MCP stdio transports intentionally support arbitrary local commands so
connectors can run custom servers. This module does not try to sandbox
that capability. It blocks two high-signal abuse shapes seen in the wild
against MCP systems:

1. The exfiltration shape (#45620): a shell interpreter whose inline
   script invokes network egress tooling.

2. The persistence shape from the June 2026 hermes-0day campaign: a
   shell interpreter whose inline script writes to OS persistence
   surfaces (``~/.ssh/authorized_keys``, ``/etc/ssh``, ``/etc/pam.d``,
   ``sudoers``, crontab, shell rc files).

3. A hardcoded indicator-of-compromise (IOC) blocklist for that
   campaign — the attacker's hermes-0day SSH public key and source IPs.
   Any entry whose command/args/env carry an IOC is refused outright.

These checks run BOTH at save time (when a connection is created or
updated via the API) and at spawn time (when MCPClientManager prepares
to dial a server), so a hand-edited or pre-planted entry is also caught
before it can execute.
"""

from __future__ import annotations

import os
import re
import shlex
from typing import TYPE_CHECKING, Any

from app.agent.tools.mcp.connectors.spec import ConnectorSpec

if TYPE_CHECKING:
    from app.agent.tools.mcp.client import ResolvedConnection

_SHELL_INTERPRETERS = frozenset({
    "bash",
    "sh",
    "zsh",
    "dash",
    "fish",
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
})

_EGRESS_PATTERN = re.compile(
    r"(?<![\w.-])(?:curl|wget|nc|ncat|socat)(?![\w.-])"
    r"|/dev/tcp/"
    r"|\bInvoke-WebRequest\b"
    r"|\bInvoke-RestMethod\b"
    r"|\bSystem\.Net\.WebClient\b",
    re.IGNORECASE,
)

_EXFIL_HINT_PATTERN = re.compile(
    r"\.env\b|--data-binary|--data-raw|\b-X\s+POST\b|\bPOST\b|<\s*[^\s]+",
    re.IGNORECASE,
)

_PERSISTENCE_PATTERN = re.compile(
    r"authorized_keys"
    r"|\.ssh/"
    r"|/etc/ssh\b"
    r"|/etc/pam\.d\b|pam_[\w-]+\.so"
    r"|/etc/sudoers"
    r"|/etc/cron|crontab\b"
    r"|/etc/rc\.local|/etc/systemd"
    r"|\.bashrc\b|\.bash_profile\b|\.profile\b|\.zshrc\b",
    re.IGNORECASE,
)

_IOC_SUBSTRINGS = (
    "AAAAC3NzaC1lZDI1NTE5AAAAICBoh1oDC4DnsO1m5mJ4yfEKrQebaFh",
    "hermes-0day",
    "60.165.167.",
    "118.182.244.156",
    "61.178.123.196",
)

_SUSPICIOUS_CREDENTIAL_PATTERNS = re.compile(
    r"[\s;|&`$(){}\[\]<>]"
    r"|(?:bash|sh|zsh|python|perl|ruby|powershell|cmd)\s+"
    r"|(?:curl|wget|nc|ncat|socat)\s",
    re.IGNORECASE,
)


def _command_basename(command: Any) -> str:
    text = str(command or "").strip()
    if not text:
        return ""
    try:
        parts = shlex.split(text, posix=(os.name != "nt"))
    except ValueError:
        parts = text.split()
    first = parts[0] if parts else text
    return os.path.basename(first).lower()


def _inline_script(args: Any) -> str:
    if args is None:
        return ""
    if isinstance(args, (list, tuple)):
        return " ".join(str(item) for item in args)
    return str(args)


def _entry_text(entry: dict[str, Any]) -> str:
    """Flatten command + args + url + server_url into one string for IOC scanning."""
    parts: list[str] = [str(entry.get("command") or "")]
    parts.append(_inline_script(entry.get("args")))
    env = entry.get("env")
    if isinstance(env, dict):
        parts.extend(str(v) for v in env.values())
    parts.append(str(entry.get("url") or ""))
    parts.append(str(entry.get("server_url") or ""))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Public validation API — dict-based (for API/user-originated entries)
# ---------------------------------------------------------------------------


def validate_mcp_server_entry(name: str, entry: dict[str, Any]) -> list[str]:
    """Return security warnings for an MCP server entry dict.

    Empty return means the entry is not suspicious. Blocks:

    * Known hermes-0day IOCs anywhere in command/args/env/url.
    * Shell interpreter whose inline script invokes network egress.
    * Shell interpreter whose inline script writes to OS persistence
      surfaces.
    """
    if not isinstance(entry, dict):
        return []

    issues: list[str] = []

    flat = _entry_text(entry)
    for ioc in _IOC_SUBSTRINGS:
        if ioc in flat:
            issues.append(
                f"MCP server '{name}' contains a known hermes-0day "
                f"indicator-of-compromise ('{ioc}')"
            )
            return issues

    command = entry.get("command")
    basename = _command_basename(command)
    if basename not in _SHELL_INTERPRETERS:
        return issues

    script = _inline_script(entry.get("args"))
    if not script:
        return issues

    if _EGRESS_PATTERN.search(script):
        issue = (
            f"MCP server '{name}' uses shell interpreter '{command}' with "
            f"network egress in args"
        )
        if _EXFIL_HINT_PATTERN.search(script):
            issue += " and exfiltration-shaped arguments"
        issues.append(issue)

    if _PERSISTENCE_PATTERN.search(script):
        issues.append(
            f"MCP server '{name}' uses shell interpreter '{command}' to write "
            f"to an OS persistence surface (SSH keys / PAM / sudoers / cron / "
            f"shell rc) — this is the hermes-0day backdoor shape"
        )

    return issues


def is_mcp_server_entry_suspicious(name: str, entry: dict[str, Any]) -> bool:
    """Boolean wrapper around ``validate_mcp_server_entry``."""
    return bool(validate_mcp_server_entry(name, entry))


# ---------------------------------------------------------------------------
# Public validation API — connection/spec-based (for internal runtime)
# ---------------------------------------------------------------------------


def validate_connector_config(
    slug: str,
    spec: ConnectorSpec,
    *,
    server_url: str | None = None,
    credentials: str | None = None,
) -> list[str]:
    """Return security warnings for a resolved connector config.

    Validates the connector's hardcoded command/args, user-provided
    server URL, and user-provided credentials.
    """
    issues: list[str] = []

    flat = f"{spec.command or ''} {' '.join(spec.args)} {server_url or ''} {credentials or ''}"
    for ioc in _IOC_SUBSTRINGS:
        if ioc in flat:
            issues.append(
                f"MCP connector '{slug}' contains a known hermes-0day IOC"
            )
            return issues

    basename = _command_basename(spec.command)
    if basename in _SHELL_INTERPRETERS:
        script = _inline_script(spec.args)
        if _EGRESS_PATTERN.search(script):
            issue = (
                f"MCP connector '{slug}' uses shell interpreter "
                f"'{spec.command}' with network egress in args"
            )
            if _EXFIL_HINT_PATTERN.search(script):
                issue += " and exfiltration-shaped arguments"
            issues.append(issue)

        if _PERSISTENCE_PATTERN.search(script):
            issues.append(
                f"MCP connector '{slug}' uses shell interpreter "
                f"'{spec.command}' to write to an OS persistence surface"
            )

    if credentials and _SUSPICIOUS_CREDENTIAL_PATTERNS.search(credentials):
        issues.append(
            f"MCP connector '{slug}' credential contains shell-metacharacters "
            f"or embedded command invocations"
        )

    return issues


def validate_connection(
    connection: ResolvedConnection,
) -> list[str]:
    """Return security warnings for a resolved connection ready to dial."""
    return validate_connector_config(
        connection.slug,
        connection.connector,
        server_url=connection.server_url,
        credentials=connection.credentials,
    )


def is_connection_suspicious(connection: ResolvedConnection) -> bool:
    """Boolean wrapper around ``validate_connection``."""
    return bool(validate_connection(connection))
