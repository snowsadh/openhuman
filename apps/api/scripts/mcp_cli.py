#!/usr/bin/env python3
"""MCP Marketplace CLI — test the full MCP catalog/install/revoke flow from your terminal.

Usage
-----
  # 1. Login (stores token in ~/.mcp-cli-token)
  python scripts/mcp_cli.py login --email you@example.com --password yourpass

  # 2. List your orgs and employees
  python scripts/mcp_cli.py whoami

  # 3. Browse the catalog
  python scripts/mcp_cli.py catalog list
  python scripts/mcp_cli.py catalog list --category "AI & Search"
  python scripts/mcp_cli.py catalog list --slug stripe

  # 4. See which connectors are already installed
  python scripts/mcp_cli.py connectors

  # 5. Install an API-key / PAT / none server
  python scripts/mcp_cli.py install stripe --credential sk_test_xxx
  python scripts/mcp_cli.py install "brave-search" --credential BSAtest123
  python scripts/mcp_cli.py install wikipedia  # no credential needed

  # 6. Trigger OAuth install (opens URL; you paste it in a browser)
  python scripts/mcp_cli.py oauth slack
  python scripts/mcp_cli.py oauth gmail

  # 7. Revoke
  python scripts/mcp_cli.py revoke stripe

All commands show the JSON response.  Set API_BASE_URL and OH_TOKEN env vars to
skip login / change target.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TOKEN_FILE = Path.home() / ".mcp-cli-token"


# ── Token helpers ──────────────────────────────────────────────────────────


def _load_token() -> str | None:
    if token := os.getenv("OH_TOKEN"):
        return token
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return None


def _save_token(token: str) -> None:
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)
    print(f"Token saved to {TOKEN_FILE}")


def _get_headers() -> dict[str, str]:
    token = _load_token()
    if not token:
        print("Not authenticated. Run: python scripts/mcp_cli.py login --email ... --password ...", file=sys.stderr)
        sys.exit(1)
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    url = f"{API_BASE_URL.rstrip('/')}{path}"
    headers = kwargs.pop("headers", {})
    headers.update(_get_headers())
    with httpx.Client() as client:
        resp = client.request(method, url, headers=headers, **kwargs)
    return resp


def _print(resp: httpx.Response) -> None:
    try:
        data = resp.json()
        print(json.dumps(data, indent=2, default=str))
    except Exception:
        print(resp.text)
    if not resp.is_success:
        print(f"Status: {resp.status_code}", file=sys.stderr)


# ── Commands ───────────────────────────────────────────────────────────────


def cmd_login(args: argparse.Namespace) -> None:
    """Login and store the JWT token."""
    payload = {"email": args.email, "password": args.password}
    with httpx.Client() as client:
        resp = client.post(f"{API_BASE_URL}/api/auth/login", json=payload)
    if resp.status_code != 200:
        # Maybe need to register first
        print(f"Login failed ({resp.status_code}). Attempting registration…")
        payload["name"] = args.name or args.email.split("@")[0]
        with httpx.Client() as client:
            resp = client.post(f"{API_BASE_URL}/api/auth/register", json=payload)
        if resp.status_code != 200:
            print(f"Register also failed ({resp.status_code}):")
            _print(resp)
            return
    token = resp.json().get("access_token")
    if not token:
        print("No access_token in response:")
        _print(resp)
        return
    _save_token(token)
    print("Authenticated.")


def cmd_whoami(args: argparse.Namespace) -> None:
    """Show current user, orgs, and first employee."""
    resp = _request("GET", "/api/auth/me")
    print("── User ──")
    _print(resp)
    resp2 = _request("GET", "/api/organizations")
    print("\n── Organizations ──")
    _print(resp2)
    orgs = resp2.json() if resp2.is_success else []
    if orgs:
        oid = orgs[0]["id"]
        resp3 = _request("GET", f"/api/organizations/{oid}/employees")
        print(f"\n── Employees (org {oid}) ──")
        _print(resp3)


def cmd_catalog(args: argparse.Namespace) -> None:
    """List / filter / inspect catalog entries."""
    if args.action == "list":
        _catalog_list(args)
    else:
        print(f"Unknown catalog action: {args.action}")


def _catalog_list(args: argparse.Namespace) -> None:
    """Fetch all catalog entries, optionally filtered."""
    # Need an org_id to call the catalog endpoint
    org_id = _resolve_org_id(args)
    if not org_id:
        return
    resp = _request("GET", f"/api/organizations/{org_id}/mcp-catalog")
    if not resp.is_success:
        _print(resp)
        return
    data = resp.json()
    entries = data.get("entries", [])

    if args.slug:
        entries = [e for e in entries if args.slug in (e.get("slug") or "")]
    if args.category and args.category != "All":
        entries = [e for e in entries if (e.get("category") or "") == args.category]

    if not entries:
        print("No matching catalog entries found.")
        return

    # Pretty table
    print(f"{'Slug':<22} {'Auth':<12} {'Installed':<10}  Name")
    print("-" * 80)
    for e in entries:
        slug = e["slug"]
        auth = e.get("auth_type", "?")
        installed = "✓" if e.get("is_installed") else "✗"
        name = e.get("name", "")
        print(f"{slug:<22} {auth:<12} {installed:<10}  {name}")


def cmd_connectors(args: argparse.Namespace) -> None:
    """Show all connectors with connection status."""
    org_id = _resolve_org_id(args)
    if not org_id:
        return
    resp = _request("GET", f"/api/organizations/{org_id}/mcp-connectors")
    if not resp.is_success:
        _print(resp)
        return
    data = resp.json()
    print(f"{'Slug':<22} {'Auth':<14} {'Connected':<10}  Name")
    print("-" * 80)
    for c in data:
        slug = c["slug"]
        auth = c.get("auth_type", "?")
        conn = "✓" if c.get("is_connected") else "✗"
        name = c.get("name", "")
        print(f"{slug:<22} {auth:<14} {conn:<10}  {name}")


def cmd_install(args: argparse.Namespace) -> None:
    """Install an API-key / PAT / none MCP server."""
    org_id, emp_id = _resolve_ids(args)
    if not org_id or not emp_id:
        return

    # Determine auth_type from catalog
    auth_type = args.auth_type or _detect_auth_type(org_id, args.slug)

    payload: dict = {
        "credential": args.credential or "",
        "auth_type": auth_type,
        "scopes": [],
        "org_wide": False,
    }
    if args.server_url:
        payload["server_url"] = args.server_url

    resp = _request(
        "POST",
        f"/api/organizations/{org_id}/employees/{emp_id}/mcp-connections/{args.slug}",
        json=payload,
    )
    if resp.status_code == 201:
        print(f"✓ Installed '{args.slug}'")
    _print(resp)


def cmd_oauth(args: argparse.Namespace) -> None:
    """Trigger OAuth install — prints or opens the authorize URL."""
    org_id, emp_id = _resolve_ids(args)
    if not org_id or not emp_id:
        return

    base = API_BASE_URL.rstrip("/")
    redirect_to = args.redirect_to or ""
    params = urlencode({"redirect_to": redirect_to}) if redirect_to else ""
    url = (
        f"{base}/api/organizations/{org_id}/employees/{emp_id}"
        f"/mcp-connections/{args.slug}/install"
    )
    if params:
        url += f"?{params}"

    # Need to follow redirect to get the authorize URL
    token = _load_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(headers=headers, follow_redirects=False) as client:
        resp = client.get(url)

    if resp.status_code in (303, 302):
        auth_url = resp.headers.get("Location", "")
        print(f"Authorize URL:\n{auth_url}")
        if args.browser:
            webbrowser.open(auth_url)
    else:
        _print(resp)


def cmd_revoke(args: argparse.Namespace) -> None:
    """Revoke (disconnect) an MCP server."""
    org_id, emp_id = _resolve_ids(args)
    if not org_id or not emp_id:
        return
    resp = _request(
        "DELETE",
        f"/api/organizations/{org_id}/employees/{emp_id}/mcp-connections/{args.slug}",
    )
    if resp.status_code == 204:
        print(f"✓ Revoked '{args.slug}'")
    else:
        _print(resp)


# ── Helpers ────────────────────────────────────────────────────────────────


def _resolve_org_id(args: argparse.Namespace) -> str | None:
    if args.org_id:
        return args.org_id
    resp = _request("GET", "/api/organizations")
    if not resp.is_success:
        _print(resp)
        return None
    orgs = resp.json()
    if not orgs:
        print("No organizations found. Create one first via the frontend.", file=sys.stderr)
        return None
    return orgs[0]["id"]


def _resolve_ids(args: argparse.Namespace) -> tuple[str | None, str | None]:
    org_id = _resolve_org_id(args)
    if not org_id:
        return None, None
    if args.emp_id:
        return org_id, args.emp_id
    resp = _request("GET", f"/api/organizations/{org_id}/employees")
    if not resp.is_success:
        _print(resp)
        return org_id, None
    emps = resp.json()
    if not emps:
        print(f"No employees found in org {org_id}. Create one via the frontend.", file=sys.stderr)
        return org_id, None
    return org_id, emps[0]["id"]


def _detect_auth_type(org_id: str, slug: str) -> str | None:
    """Look up the default auth type from the catalog for a slug."""
    resp = _request("GET", f"/api/organizations/{org_id}/mcp-catalog")
    if not resp.is_success:
        return None
    data = resp.json()
    for e in data.get("entries", []):
        if e["slug"] == slug:
            at = e.get("auth_type", "")
            # Map catalog auth types to connector auth types
            mapping = {
                "none": "none",
                "api_key": "api_key_header",
                "pat": "pat_bearer",
                "pat_bearer": "pat_bearer",
                "oauth2": None,  # OAuth2 installs via cmd_oauth not cmd_install
            }
            return mapping.get(at)
    return None


# ── CLI entry point ────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP Marketplace CLI")
    parser.add_argument("--org-id", help="Organization UUID (auto-resolve if omitted)")
    parser.add_argument("--emp-id", help="Employee UUID (auto-resolve if omitted)")

    sub = parser.add_subparsers(dest="command", required=True)

    # login
    p = sub.add_parser("login", help="Login (or register) and store JWT")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--name")

    # whoami
    sub.add_parser("whoami", help="Show current user, orgs, and employees")

    # catalog
    p = sub.add_parser("catalog", help="Browse the MCP catalog")
    p.add_argument("action", nargs="?", default="list", choices=["list"])
    p.add_argument("--slug", help="Filter by slug")
    p.add_argument("--category", choices=["All", "Productivity", "Development", "Data & DBs", "Communication", "AI & Search"], default="All")

    # connectors
    sub.add_parser("connectors", help="List all connectors with install status")

    # install
    p = sub.add_parser("install", help="Install an API-key/PAT MCP server")
    p.add_argument("slug", help="Connector slug (e.g. stripe, brave-search)")
    p.add_argument("--credential", help="API key or PAT")
    p.add_argument("--auth-type", choices=["api_key_header", "pat_bearer", "none"])
    p.add_argument("--server-url", help="Custom server URL (for n8n etc.)")

    # oauth
    p = sub.add_parser("oauth", help="Trigger OAuth install flow")
    p.add_argument("slug", help="Connector slug (e.g. slack, gmail)")
    p.add_argument("--browser", action="store_true", help="Open the authorize URL in your browser")
    p.add_argument("--redirect-to", help="URL to redirect back to after OAuth")

    # revoke
    p = sub.add_parser("revoke", help="Revoke/disconnect an installed MCP server")
    p.add_argument("slug", help="Connector slug")

    args = parser.parse_args()

    dispatch = {
        "login": cmd_login,
        "whoami": cmd_whoami,
        "catalog": cmd_catalog,
        "connectors": cmd_connectors,
        "install": cmd_install,
        "oauth": cmd_oauth,
        "revoke": cmd_revoke,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
