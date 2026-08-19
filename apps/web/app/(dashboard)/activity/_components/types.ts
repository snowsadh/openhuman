export interface ActivityEventResponse {
  id: string;
  event_type: string;
  summary: string;
  description: string | null;
  employee_id: string | null;
  employee_name: string | null;
  platform: string | null;
  status: string | null;
  metadata: Record<string, unknown> | null;
  occurred_at: string;
}

export interface ActivityFeedResponse {
  events: ActivityEventResponse[];
  total: number;
  next_offset: number | null;
}

export interface ActivityStatsResponse {
  total_today: number;
  agent_runs: number;
  document_uploads: number;
  employee_events: number;
  tool_usages: number;
  human_escalations: number;
  memory_operations: number;
}
