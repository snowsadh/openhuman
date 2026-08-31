"use client";

import {
  Activity,
  CheckCircle2,
  CircleAlert,
  Clock3,
  ExternalLink,
  RefreshCw,
  ShieldCheck,
  ShieldX,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useOrgStore } from "@/stores/org";

type RankedItem = { name: string; count: number };
type RecentPlan = {
  plan_hash: string | null;
  agent: string | null;
  occurred_at: string;
  url: string;
};
type Metrics = {
  status: string;
  total_plans: number;
  total_calls: number;
  allow_count: number;
  hold_count: number;
  block_count: number;
  executed_count: number;
  failed_count: number;
  pending_approvals: number;
  allow_percent: number;
  hold_percent: number;
  block_percent: number;
  top_agents: RankedItem[];
  top_mcps: RankedItem[];
  top_tools: RankedItem[];
  recent_plans: RecentPlan[];
  registration_healthy: boolean;
  telemetry_healthy: boolean;
};
type Approval = {
  id: string;
  plan_hash: string;
  delegation_id: string | null;
  mcp: string;
  action: string;
  redacted_parameters: Record<string, unknown>;
  requester_email: string | null;
  status: string;
  reason: string | null;
  armoriq_url: string | null;
  expires_at: string;
  created_at: string;
};

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("oh_token");
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  detail: string;
  icon: typeof Activity;
}) {
  return (
    <div className="rounded-xl border border-border bg-card/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </p>
          <p className="mt-2 text-3xl font-semibold tracking-tight">{value}</p>
          <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
        </div>
        <Icon className="size-5 text-primary" />
      </div>
    </div>
  );
}

function Ranking({ title, items }: { title: string; items: RankedItem[] }) {
  return (
    <div className="rounded-xl border border-border bg-card/60 p-4">
      <h2 className="text-sm font-semibold">{title}</h2>
      <div className="mt-4 space-y-3">
        {items.length ? (
          items.map((item) => (
            <div key={item.name} className="flex items-center justify-between gap-3 text-sm">
              <span className="truncate text-muted-foreground">{item.name}</span>
              <span className="rounded-md bg-muted px-2 py-0.5 font-medium">{item.count}</span>
            </div>
          ))
        ) : (
          <p className="text-sm text-muted-foreground">No governed calls yet.</p>
        )}
      </div>
    </div>
  );
}

export default function ArmorIQPage() {
  const orgId = useOrgStore((state) => state.orgId);
  const metricsQuery = useQuery({
    queryKey: ["armoriq-metrics", orgId],
    enabled: Boolean(orgId),
    refetchInterval: 15000,
    queryFn: async () => {
      const response = await fetch(
        `/api/agent/armoriq/metrics?organization_id=${orgId}`,
        { headers: authHeaders() },
      );
      if (!response.ok) throw new Error("Could not load ArmorIQ metrics");
      return response.json() as Promise<Metrics>;
    },
  });
  const approvalsQuery = useQuery({
    queryKey: ["armoriq-approvals", orgId],
    enabled: Boolean(orgId),
    refetchInterval: 15000,
    queryFn: async () => {
      const response = await fetch(
        `/api/approvals?organization_id=${orgId}&status=pending`,
        { headers: authHeaders() },
      );
      if (!response.ok) throw new Error("Could not load ArmorIQ approvals");
      return response.json() as Promise<{ items: Approval[] }>;
    },
  });
  const metrics = metricsQuery.data ?? null;
  const approvals = approvalsQuery.data?.items ?? [];
  const loading = metricsQuery.isLoading || approvalsQuery.isLoading;
  const error = metricsQuery.error ?? approvalsQuery.error;

  const refresh = () =>
    Promise.all([metricsQuery.refetch(), approvalsQuery.refetch()]);

  const openAuthority = async (approval: Approval, action: "approve" | "reject") => {
    const response = await fetch(`/api/approvals/${approval.id}/${action}`, {
      method: "POST",
      headers: authHeaders(),
    });
    if (response.ok) {
      const payload = (await response.json()) as { approval: Approval };
      window.open(payload.approval.armoriq_url ?? approval.armoriq_url ?? "", "_blank");
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center">
        <Spinner className="size-9" />
      </div>
    );
  }

  return (
    <div className="px-4 py-6 sm:px-8 sm:py-10">
      <div className="mx-auto max-w-7xl">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-primary">
              <ShieldCheck className="size-4" /> ArmorIQ governance
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">Trust & approvals</h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              Every external MCP action is bound to a signed plan. ArmorIQ decides allow,
              hold, or block before the connector receives the call.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refresh()}>
            <RefreshCw className="size-4" /> Refresh
          </Button>
        </div>

        {error ? (
          <div className="mt-6 rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
            {error instanceof Error ? error.message : "ArmorIQ data unavailable"}
          </div>
        ) : null}

        {metrics && (
          <>
            <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <MetricCard label="Signed plans" value={metrics.total_plans} detail="Captured by IAP" icon={Activity} />
              <MetricCard label="Allowed" value={metrics.allow_count} detail={`${metrics.allow_percent}% of decisions`} icon={CheckCircle2} />
              <MetricCard label="Held" value={metrics.hold_count} detail={`${metrics.hold_percent}% need approval`} icon={Clock3} />
              <MetricCard label="Blocked" value={metrics.block_count} detail={`${metrics.block_percent}% stopped`} icon={ShieldX} />
              <MetricCard label="Executed" value={metrics.executed_count} detail={`${metrics.failed_count} failed`} icon={ShieldCheck} />
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <div className={`rounded-xl border p-4 ${metrics.registration_healthy ? "border-emerald-500/30 bg-emerald-500/5" : "border-amber-500/30 bg-amber-500/5"}`}>
                <div className="flex items-center gap-2 text-sm font-medium">
                  {metrics.registration_healthy ? <CheckCircle2 className="size-4 text-emerald-500" /> : <CircleAlert className="size-4 text-amber-500" />}
                  AWS ↔ ArmorIQ registration
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{metrics.registration_healthy ? "Credentials and HTTPS MCP URL are configured." : "Registration configuration is incomplete."}</p>
              </div>
              <div className={`rounded-xl border p-4 ${metrics.telemetry_healthy ? "border-emerald-500/30 bg-emerald-500/5" : "border-amber-500/30 bg-amber-500/5"}`}>
                <div className="flex items-center gap-2 text-sm font-medium">
                  {metrics.telemetry_healthy ? <CheckCircle2 className="size-4 text-emerald-500" /> : <CircleAlert className="size-4 text-amber-500" />}
                  Decision telemetry
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{metrics.telemetry_healthy ? "Governance events arrived during the last 24 hours." : "No recent governance telemetry was found."}</p>
              </div>
            </div>

            <section className="mt-8">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold">Pending approvals</h2>
                <span className="text-xs text-muted-foreground">{metrics.pending_approvals} waiting</span>
              </div>
              <div className="mt-3 overflow-hidden rounded-xl border border-border">
                {approvals.length ? approvals.map((approval) => (
                  <div key={approval.id} className="border-b border-border p-4 last:border-b-0">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{approval.mcp}.{approval.action}</span>
                          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-600">hold</span>
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground">{approval.reason ?? "Human approval required"}</p>
                        <p className="mt-2 font-mono text-[11px] text-muted-foreground">plan {approval.plan_hash.slice(0, 18)}… · delegation {approval.delegation_id ?? "pending"}</p>
                        <pre className="mt-3 max-w-2xl overflow-auto rounded-lg bg-muted/60 p-3 text-xs">{JSON.stringify(approval.redacted_parameters, null, 2)}</pre>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => void openAuthority(approval, "approve")}>Review approval <ExternalLink className="size-3.5" /></Button>
                        <Button size="sm" variant="outline" onClick={() => void openAuthority(approval, "reject")}>Review rejection</Button>
                      </div>
                    </div>
                  </div>
                )) : (
                  <div className="p-10 text-center text-sm text-muted-foreground">No actions are waiting for approval.</div>
                )}
              </div>
            </section>

            <div className="mt-8 grid gap-3 md:grid-cols-3">
              <Ranking title="Top agents" items={metrics.top_agents} />
              <Ranking title="Top MCPs" items={metrics.top_mcps} />
              <Ranking title="Top tools" items={metrics.top_tools} />
            </div>

            <section className="mt-8 rounded-xl border border-border bg-card/60 p-4">
              <h2 className="text-sm font-semibold">Recent signed plans</h2>
              <div className="mt-3 divide-y divide-border">
                {metrics.recent_plans.length ? metrics.recent_plans.map((plan, index) => (
                  <a key={`${plan.plan_hash}-${index}`} href={plan.url} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-4 py-3 text-sm hover:text-primary">
                    <span className="truncate font-mono text-xs">{plan.plan_hash ?? "plan pending"}</span>
                    <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">{plan.agent ?? "OpenHuman"} <ExternalLink className="size-3" /></span>
                  </a>
                )) : <p className="py-5 text-sm text-muted-foreground">No signed plans yet.</p>}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
