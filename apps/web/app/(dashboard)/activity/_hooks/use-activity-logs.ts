"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ActivityEventResponse } from "../_components/types";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const LIMIT = 50;

async function fetchActivityEvents(
  orgId: string,
  params: {
    employeeId?: string;
    employeeType?: string;
    level?: string;
    search?: string;
    offset?: number;
  },
  getToken: () => Promise<string | null>,
): Promise<{ data: ActivityEventResponse[]; total: number }> {
  const searchParams = new URLSearchParams({
    organization_id: orgId,
    limit: String(LIMIT),
    offset: String(params.offset ?? 0),
  });
  if (params.employeeId) searchParams.set("employee_id", params.employeeId);
  if (params.employeeType) searchParams.set("employee_type", params.employeeType);
  if (params.search) searchParams.set("q", params.search);
  if (params.level) {
    const types = levelToEventTypes(params.level);
    if (types.length > 0) {
      types.forEach((t) => searchParams.append("event_types", t));
    }
  }

  const token = await getToken();
  const response = await fetch(
    `${API_URL}/api/activity?${searchParams.toString()}`,
    {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    },
  );

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  const json = await response.json();
  return { data: json.events, total: json.total };
}

/** Maps level filter to our event types. Must stay in sync with eventTypeToLevel(). */
function levelToEventTypes(level: string): string[] {
  switch (level) {
    case "trace":
      return []; // No event types map to trace — returns all
    case "debug":
      return [
        "ai_engine",
        "tool_usage",
        "memory_operation",
        "mcp_connected",
        "channel_assigned",
        "channel_unassigned",
      ];
    case "info":
      return [
        "agent_run",
        "agent_conversation",
        "document_upload",
        "employee_created",
        "employee_updated",
        "org_created",
        "org_updated",
        "slack_oauth",
      ];
    case "warn":
      return ["human_escalation", "org_deleted"];
    case "error":
    case "fatal":
      return []; // No event types map to error/fatal — returns all but won't crash
    default:
      return [level];
  }
}

export function useActivityLogs(
  orgId: string,
  getToken: () => Promise<string | null>,
  params: {
    employeeId?: string;
    employeeType?: string;
    level?: string;
    search?: string;
  },
) {
  const { employeeId, employeeType, level, search = "" } = params;

  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [entries, setEntries] = useState<ActivityEventResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // Debounce search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(
      () => setDebouncedSearch(search),
      300,
    );
    return () => clearTimeout(debounceRef.current);
  }, [search]);

  // Request counter to discard stale in-flight responses
  const requestIdRef = useRef(0);
  // Guard against concurrent "Load more" calls
  const loadingMoreRef = useRef(false);

  const load = useCallback(
    async (
      currentOffset: number,
      options?: { append?: boolean; background?: boolean },
    ) => {
      if (!orgId) return;
      const append = options?.append ?? false;
      const background = options?.background ?? false;

      // Prevent concurrent loadMore calls
      if (append && loadingMoreRef.current) return;
      if (append) loadingMoreRef.current = true;

      if (background) {
        setRefreshing(true);
      } else if (currentOffset === 0) {
        setLoading(true);
      } else {
        setLoadingMore(true);
      }

      const thisRequestId = ++requestIdRef.current;

      try {
        const result = await fetchActivityEvents(
          orgId,
          {
            employeeId,
            employeeType,
            level: level || undefined,
            search: debouncedSearch || undefined,
            offset: currentOffset,
          },
          getToken,
        );

        // Discard stale responses
        if (thisRequestId !== requestIdRef.current) return;

        setTotal(result.total);
        setOffset(currentOffset + result.data.length);

        if (append) {
          setEntries((prev) => [...prev, ...result.data]);
        } else {
          setEntries(result.data);
        }
      } catch {
        // Request failed — only clear on initial load, keep stale on append
        if (!append) {
          setEntries([]);
          setTotal(0);
        }
      } finally {
        if (thisRequestId === requestIdRef.current) {
          if (!background) setLoading(false);
          if (append) setLoadingMore(false);
          if (background) setRefreshing(false);
        }
        if (append) loadingMoreRef.current = false;
      }
    },
    [orgId, employeeId, employeeType, level, debouncedSearch, getToken],
  );

  // Reload when filters change
  const prevFiltersRef = useRef("");
  useEffect(() => {
    const key = `${employeeId ?? ""}|${employeeType ?? ""}|${level ?? ""}|${debouncedSearch}`;
    if (key !== prevFiltersRef.current) {
      prevFiltersRef.current = key;
      setEntries([]);
      setOffset(0);
      load(0);
    } else if (prevFiltersRef.current === "" && !key) {
      // Initial load
      load(0);
      prevFiltersRef.current = "loaded";
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employeeId, employeeType, level, debouncedSearch]);

  const loadMore = useCallback(() => {
    if (offset < total && !loadingMoreRef.current) {
      load(offset, { append: true });
    }
  }, [offset, total, load]);

  const refresh = useCallback(async () => {
    await load(0, { background: true });
  }, [load]);

  return {
    entries,
    total,
    loading,
    loadingMore,
    refreshing,
    hasMore: offset < total,
    loadMore,
    refresh,
  };
}
