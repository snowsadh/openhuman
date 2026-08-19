#!/usr/bin/env python3
"""
Generate one-click Slack App creation URLs for your employees.
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path

def build_manifest(employee_name: str, redirect_domain: str) -> dict:
    redirect_domain = redirect_domain.strip().rstrip("/")
    if not redirect_domain.startswith("http://") and not redirect_domain.startswith("https://"):
        redirect_domain = f"https://{redirect_domain}"

    redirect_url = f"{redirect_domain}/api/slack/oauth/callback"

    return {
        "display_information": {
            "name": employee_name,
            "description": f"OpenHuman AI employee — {employee_name}",
            "background_color": "#1a1a2e"
        },
        "features": {
            "bot_user": {
                "display_name": employee_name,
                "always_online": True
            }
        },
        "oauth_config": {
            "redirect_urls": [
                redirect_url
            ],
            "scopes": {
                "bot": [
                    "app_mentions:read",
                    "channels:history",
                    "channels:join",
                    "groups:history",
                    "chat:write",
                    "chat:write.customize",
                    "im:history",
                    "im:write",
                    "mpim:history",
                    "mpim:write",
                    "users:read"
                ]
            }
        },
        "settings": {
            "socket_mode_enabled": True,
            "event_subscriptions": {
                "bot_events": [
                    "app_mention",
                    "message.im",
                    "message.groups",
                    "message.mpim",
                    "message.channels"
                ]
            },
            "org_deploy_enabled": False
        }
    }

def main():
    parser = argparse.ArgumentParser(description="Generate one-click Slack App creation URLs.")
    parser.add_argument("--domain", type=str, required=True, help="Your Railway API domain (e.g. openhuman-api-production.up.railway.app)")
    args = parser.parse_args()

    employees = [
        "SnowBot",
        "Alex (HR)",
        "Blake (Sales)",
        "Casey (Support)",
        "Drew (General)"
    ]

    print("\n==================================================================")
    print("      ONE-CLICK SLACK APP CREATION LINKS FOR YOUR EMPLOYEES       ")
    print("==================================================================\n")
    print("Instructions:")
    print("1. Click the link for the employee you want to configure.")
    print("2. Slack will open with the manifest pre-filled. Click 'Create App'.")
    print("3. Retrieve the Client ID, Client Secret, and generate an App-Level Token.")
    print("4. Save those credentials to the slot using our configure script.")
    print("------------------------------------------------------------------\n")

    for emp in employees:
        manifest = build_manifest(emp, args.domain)
        manifest_str = json.dumps(manifest, indent=2)
        
        print(f"==================================================================")
        print(f"👤 Employee: {emp}")
        print(f"==================================================================")
        print("1. Open this page in your browser:")
        print("   👉 https://api.slack.com/apps?new_app=1")
        print("2. Choose 'From an app manifest', select your workspace, and paste this JSON:")
        print("```json")
        print(manifest_str)
        print("```")
        print("\n")

if __name__ == "__main__":
    main()
