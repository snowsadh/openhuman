# ArmorIQ configuration as code

The five production manifests are the source of truth for OpenHuman's live,
public role MCP endpoints. Runtime startup validates credentials but never
registers or changes policy. User-authorized SaaS MCPs are added to these
manifests only after OAuth setup, tool discovery, and an ArmorIQ smoke test;
until then they remain fail-closed in the marketplace.

Set the API key, MCP bearer token, and role URLs, then run:

```bash
for config in deploy/armoriq/production/*.yaml; do
  armoriq validate --config "$config"
  armoriq register --config "$config"
done
```

The role URLs use the AWS CloudFront domain:

- `ARMORIQ_GENERAL_MCP_URL=https://<distribution>/api/agent/armoriq/mcp`
- `ARMORIQ_HR_MCP_URL=https://<distribution>/api/agent/armoriq/mcp/hr`
- `ARMORIQ_SALES_MCP_URL=https://<distribution>/api/agent/armoriq/mcp/sales`
- `ARMORIQ_SUPPORT_MCP_URL=https://<distribution>/api/agent/armoriq/mcp/support`
- `ARMORIQ_LEGAL_MCP_URL=https://<distribution>/api/agent/armoriq/mcp/legal`

Approval tools are registered in each role manifest and the organization policy
turns those tools into `require_approval` decisions. Unlisted tools remain
denied by default.

`policies/openhuman-production.json` is the organization policy profile. It is
deny-by-default and includes role-scoped permit, require-approval, and forbid
statements. CI activates it only after all five MCP manifests validate and
register successfully.
