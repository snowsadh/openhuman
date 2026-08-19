export const LEVEL_COLORS: Record<string, string> = {
  trace: "bg-gray-100 text-gray-700",
  debug: "bg-blue-100 text-blue-700",
  info: "bg-blue-100 text-blue-700",
  warn: "bg-amber-100 text-amber-700",
  error: "bg-red-100 text-red-700",
  fatal: "bg-red-200 text-red-800",
};

/** Map our activity event_type to a log level for badge coloring. */
export function eventTypeToLevel(
  eventType: string,
): "trace" | "debug" | "info" | "warn" | "error" | "fatal" {
  switch (eventType) {
    // Debug level — internal operations
    case "ai_engine":
    case "tool_usage":
    case "memory_operation":
    case "mcp_connected":
    case "channel_assigned":
    case "channel_unassigned":
      return "debug";
    // Warn level — needs attention
    case "human_escalation":
    case "org_deleted":
      return "warn";
    // Info level — normal activity
    case "agent_run":
    case "agent_conversation":
    case "document_upload":
    case "employee_created":
    case "employee_updated":
    case "org_created":
    case "org_updated":
    case "slack_oauth":
      return "info";
    default:
      return "info";
  }
}
