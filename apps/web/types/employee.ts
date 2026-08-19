import type { EmployeeResponse } from "@repo/api-client";

export interface EmployeeDisplay {
  id: string;
  orgId: string;
  name: string;
  employeeType: string | null;
  role: string;
  specialization: string;
  duties: string[];
  status: string;
  hasDiscord: boolean;
  hasSlack: boolean;
  hasClickup?: boolean;
  deployedAt: string;
  currentTask: string | null;
  mcpConnectionSlugs: string[];
}

function castDuties(duties: unknown[] | null | undefined): string[] {
  if (!duties) return [];
  return duties.filter((d): d is string => typeof d === "string");
}

function realMcpSlugs(mcpConnections: unknown[] | null | undefined): string[] {
  if (mcpConnections && mcpConnections.length > 0) {
    const slugs: string[] = [];
    for (const conn of mcpConnections) {
      if (
        conn &&
        typeof conn === "object" &&
        "connector_slug" in conn &&
        typeof (conn as Record<string, unknown>).connector_slug === "string"
      ) {
        slugs.push((conn as Record<string, unknown>).connector_slug as string);
      }
    }
    return slugs;
  }
  return [];
}

export function apiToEmployeeDisplay(api: EmployeeResponse): EmployeeDisplay {
  return {
    id: api.id,
    orgId: api.org_id,
    name: api.name,
    employeeType: api.employee_type ?? null,
    role: api.role ?? "",
    specialization: api.specialization ?? "",
    duties: castDuties(api.duties),
    status: api.operational_status ?? (api.status === "active" ? "idle" : api.status),
    hasDiscord: api.has_discord_token,
    hasSlack: api.has_slack_token,
    hasClickup: false,
    deployedAt: api.created_at,
    currentTask: api.current_task ?? null,
    mcpConnectionSlugs: realMcpSlugs(api.mcp_connections),
  };
}

const STATUS_DISPLAY: Record<string, { label: string; dotColor: string }> = {
  active: { label: "Working", dotColor: "bg-green-500" },
  training: { label: "Working", dotColor: "bg-green-500" },
  idle: { label: "Idle", dotColor: "bg-amber-400" },
  inactive: { label: "Inactive", dotColor: "bg-muted-foreground/30" },
  suspended: { label: "Suspended", dotColor: "bg-red-500" },
  working: { label: "Working", dotColor: "bg-green-500" },
  attention: { label: "Needs attention", dotColor: "bg-red-500" },
  offline: { label: "Offline", dotColor: "bg-muted-foreground/30" },
};

const FALLBACK_STATUS = {
  label: "Unknown",
  dotColor: "bg-muted-foreground/30",
};

export function getStatusConfig(status: string) {
  return STATUS_DISPLAY[status] ?? FALLBACK_STATUS;
}

export const EMPLOYEE_TYPE_LABELS: Record<string, string> = {
  "legal-compliance": "Legal & Compliance",
  support: "Customer Support",
  hr: "HR Specialist",
  general: "General Assistant",
  sales: "Sales Representative",
};
