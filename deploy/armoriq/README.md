# ArmorIQ configuration as code

The five production manifests are the source of truth for OpenHuman's role
MCP endpoints. Runtime startup validates credentials but never registers or
changes policy.

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

Approval tools remain denied in these baseline manifests until the governance
checkpoint installs explicit ArmorIQ hold policies. This preserves fail-closed
behavior during staged deployment.
