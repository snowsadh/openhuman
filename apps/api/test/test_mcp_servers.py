#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path

# Ensure app package is importable
_this_dir = Path(__file__).resolve().parent
_api_dir = _this_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

if _api_dir.joinpath(".env").exists():
    from dotenv import load_dotenv
    load_dotenv(_api_dir / ".env")

from app.agent.tools.mcp.client import MCPClientManager, ResolvedConnection
from app.agent.tools.mcp.connectors.registry import REGISTRY

async def test_all_servers():
    print("🔌 Starting MCP Server connectivity tests...\n")
    
    # We will build a list of connections to test based on available registry and credentials
    connections = []
    
    # Define credentials mapping from environment variables
    # e.g., GITHUB_PAT, NOTION_TOKEN, VERCEL_TOKEN
    credentials_map = {
        "github": os.getenv("GITHUB_PAT") or os.getenv("GITHUB_TOKEN"),
        "notion": os.getenv("NOTION_TOKEN") or os.getenv("NOTION_INTEGRATION_TOKEN"),
        "vercel": os.getenv("VERCEL_TOKEN"),
        "web_search": None, # none needed
        "gmail": os.getenv("GMAIL_TOKEN"), # OAuth access token for testing
        "gamma": os.getenv("GAMMA_TOKEN"), # OAuth access token for testing
    }
    
    for slug, spec in REGISTRY.items():
        print(f"📦 Found connector '{slug}':")
        print(f"   Name        : {spec.name}")
        print(f"   Transport   : {spec.transport}")
        print(f"   Auth Type   : {spec.auth_type}")
        print(f"   Base URL    : {spec.base_url}")
        
        creds = credentials_map.get(slug)
        if spec.auth_type != "none" and not creds:
            print(f"   ⚠️  Skipping: No credentials found in env. Set env var for auth type '{spec.auth_type}' (e.g. GITHUB_PAT, NOTION_TOKEN, VERCEL_TOKEN).\n")
            continue
            
        connections.append(
            ResolvedConnection(
                slug=slug,
                connector=spec,
                credentials=creds,
            )
        )
        print("   ✅ Queued for connection test.\n")

    if not connections:
        print("❌ No MCP servers were queued for testing. Please set relevant environment variables.")
        return

    print("⚡ Connecting to queued MCP servers...")
    mgr = MCPClientManager()
    try:
        tools = await mgr.connect(connections)
        print("\n🎉 Connection results:")
        print("=" * 60)
        if not tools:
            print("   No tools loaded (connections might have timed out or failed).")
        else:
            print(f"   Successfully loaded {len(tools)} tools:")
            for tool in tools:
                print(f"   - {tool.name}")
                print(f"     Description: {tool.description.splitlines()[0] if tool.description else 'No description'}")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Error during connection: {e}")
    finally:
        await mgr.disconnect()

if __name__ == "__main__":
    asyncio.run(test_all_servers())
