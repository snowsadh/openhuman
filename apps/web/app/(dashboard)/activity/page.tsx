"use client";

import { RefreshCw, Search } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useEmployeesListEmployeesRoute } from "@repo/api-client";

import { LogCard } from "@/components/log-card";
import { Spinner } from "@/components/ui/spinner";
import { Button } from "@/components/ui/button";
import { useOrgStore } from "@/stores/org";
import { useActivityLogs } from "./_hooks/use-activity-logs";

const LEVELS = ["trace", "debug", "info", "warn", "error", "fatal"] as const;
const BOT_TYPE_LABELS: Record<string, string> = {
  general: "General",
  hr: "HR",
  support: "Support",
  sales: "Sales",
  "legal-compliance": "Legal & Compliance",
};

function readEmployeeId(): string | undefined {
  if (typeof window === "undefined") return undefined;
  return (
    new URLSearchParams(window.location.search).get("employeeId") || undefined
  );
}

export default function ActivityPage() {
  const orgId = useOrgStore((s) => s.orgId);
  const getToken = useCallback(async () => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("oh_token");
  }, []);

  const [search, setSearch] = useState("");
  const [level, setLevel] = useState("");
  const [botType, setBotType] = useState("");
  const [employeeId, setEmployeeId] = useState<string>(
    readEmployeeId() ?? "",
  );

  // Fetch employees for the dropdown
  const { data: apiEmployees } = useEmployeesListEmployeesRoute(orgId ?? "", {
    query: { enabled: !!orgId },
  });

  const botTypeOptions = useMemo(() => {
    const types = new Set(
      (apiEmployees ?? [])
        .map((emp) => emp.employee_type)
        .filter((value): value is string => Boolean(value)),
    );
    return Array.from(types).sort((a, b) =>
      (BOT_TYPE_LABELS[a] ?? a).localeCompare(BOT_TYPE_LABELS[b] ?? b),
    );
  }, [apiEmployees]);

  const visibleBots = useMemo(() => {
    if (!apiEmployees) return [];
    if (!botType) return apiEmployees;
    return apiEmployees.filter((emp) => emp.employee_type === botType);
  }, [apiEmployees, botType]);

  const { entries, total, loading, loadingMore, hasMore, loadMore, refreshing, refresh } =
    useActivityLogs(orgId!, getToken, {
      employeeId: employeeId || undefined,
      employeeType: botType || undefined,
      level: level || undefined,
      search,
    });

  const hasFilters =
    search.trim() !== "" || level !== "" || employeeId !== "" || botType !== "";

  const clearFilters = () => {
    setSearch("");
    setLevel("");
    setBotType("");
    setEmployeeId("");
  };

  return (
    <div className="px-4 py-6 transition-all duration-300 ease-out sm:px-8 sm:py-10">
      {loading ? (
        <div
          className="flex items-center justify-center"
          style={{ height: "calc(100vh - 80px)" }}
        >
          <Spinner className="size-9" />
        </div>
      ) : (
        <div className="mx-auto max-w-6xl">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">
              Activity
            </h1>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">
                {hasFilters
                  ? `${entries.length} of ${total} entries`
                  : `${total} entries`}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void refresh()}
                disabled={refreshing}
              >
                <RefreshCw
                  className={`size-4 ${refreshing ? "animate-spin" : ""}`}
                />
                Refresh
              </Button>
            </div>
          </div>

          {/* Filters row */}
          <div className="mt-5 flex flex-wrap items-center gap-3">
            {/* Bot type dropdown */}
            {botTypeOptions.length > 0 && (
              <select
                value={botType}
                onChange={(e) => {
                  const nextBotType = e.target.value;
                  const nextVisibleBots = !nextBotType
                    ? (apiEmployees ?? [])
                    : (apiEmployees ?? []).filter(
                        (emp) => emp.employee_type === nextBotType,
                      );
                  setBotType(nextBotType);
                  if (
                    employeeId &&
                    nextVisibleBots.every((bot) => bot.id !== employeeId)
                  ) {
                    setEmployeeId("");
                  }
                }}
                aria-label="Filter by bot type"
                className="h-9 rounded-lg border border-border bg-card/60 px-3 text-sm text-foreground outline-none transition-colors focus:border-ring focus:ring-3 focus:ring-ring/50"
              >
                <option value="">All bot types</option>
                {botTypeOptions.map((type) => (
                  <option key={type} value={type}>
                    {BOT_TYPE_LABELS[type] ?? type}
                  </option>
                ))}
              </select>
            )}

            {/* Bot dropdown */}
            {visibleBots.length > 0 && (
              <select
                value={employeeId}
                onChange={(e) => setEmployeeId(e.target.value)}
                aria-label="Filter by bot"
                className="h-9 rounded-lg border border-border bg-card/60 px-3 text-sm text-foreground outline-none transition-colors focus:border-ring focus:ring-3 focus:ring-ring/50"
              >
                <option value="">All bots</option>
                {visibleBots.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.name}
                  </option>
                ))}
              </select>
            )}

            {/* Search */}
            <div className="relative min-w-[200px] max-w-sm flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground/40" />
              <input
                type="text"
                placeholder="Search activity..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full rounded-lg border border-border bg-card/60 py-2.5 pl-9 pr-3 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/40 focus:border-ring focus:ring-3 focus:ring-ring/50"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground hover:text-foreground"
                >
                  clear
                </button>
              )}
            </div>
          </div>

          {/* Level filter */}
          <div
            className="mt-3 flex flex-wrap items-center gap-1"
            role="group"
            aria-label="Filter by log level"
          >
            <span className="mr-1 text-[11px] font-medium text-muted-foreground">
              Level
            </span>
            <button
              type="button"
              onClick={() => setLevel("")}
              aria-pressed={level === ""}
              className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
                level === ""
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
              }`}
            >
              All
            </button>
            {LEVELS.map((l) => (
              <button
                key={l}
                type="button"
                onClick={() => setLevel(level === l ? "" : l)}
                aria-pressed={level === l}
                className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
                  level === l
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                }`}
              >
                {l}
              </button>
            ))}
          </div>

          {/* Entry list */}
          <div className="mt-5 overflow-hidden rounded-xl border border-border">
            {entries.length > 0 ? (
              entries.map((entry) => (
                <LogCard key={entry.id} event={entry} />
              ))
            ) : (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <Search className="size-6 text-muted-foreground/20" />
                <p className="mt-3 text-sm text-muted-foreground">
                  {hasFilters
                    ? "No entries match your filters."
                    : "No activity yet."}
                </p>
                {hasFilters && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-3"
                    onClick={clearFilters}
                  >
                    Clear filters
                  </Button>
                )}
              </div>
            )}
          </div>

          {/* Load more */}
          {hasMore && (
            <div className="mt-4 flex justify-center">
              <Button
                variant="outline"
                size="sm"
                onClick={loadMore}
                disabled={loadingMore}
              >
                {loadingMore ? "Loading..." : "Load more"}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
