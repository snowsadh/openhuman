"use client";

import { useState } from "react";

import { formatTimestamp } from "@/lib/format-timestamp";
import { LEVEL_COLORS, eventTypeToLevel } from "@/lib/log-levels";
import type { ActivityEventResponse } from "@/app/(dashboard)/activity/_components/types";

export function LogCard({ event }: { event: ActivityEventResponse }) {
  const [expanded, setExpanded] = useState(false);
  const level = eventTypeToLevel(event.event_type);

  return (
    <div
      className="group grid cursor-pointer grid-cols-[auto_1fr_auto] items-start gap-4 border-b border-border px-4 py-4 transition-colors hover:bg-muted/30 last:border-b-0"
      onClick={() => setExpanded(!expanded)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setExpanded(!expanded);
        }
      }}
      role="button"
      tabIndex={0}
    >
      {/* Level badge */}
      <div className="flex shrink-0 items-center gap-2">
        <span
          className={`rounded-md px-2 py-0.5 text-[10px] font-medium uppercase leading-relaxed ${LEVEL_COLORS[level] || "bg-gray-100 text-gray-700"}`}
        >
          {level}
        </span>
      </div>

      {/* Body */}
      <div className="min-w-0">
        <p className="text-sm text-foreground">{event.summary}</p>
        {(event.event_type || event.employee_name || event.platform) && (
          <p className="mt-0.5 text-[11px] text-muted-foreground/60">
            {event.event_type && (
              <span className="rounded bg-muted px-1 py-px font-mono text-[10px]">
                {event.event_type}
              </span>
            )}
            {event.event_type && (event.employee_name || event.platform) && (
              <span> &middot; </span>
            )}
            {event.employee_name && <span>{event.employee_name}</span>}
            {event.employee_name && event.platform && (
              <span> &middot; </span>
            )}
            {event.platform && (
              <span className="uppercase">{event.platform}</span>
            )}
          </p>
        )}

        {expanded && (
          <pre className="mt-2 max-h-48 overflow-auto rounded bg-muted/50 p-2 text-[10px] leading-relaxed text-muted-foreground">
            {(() => {
              try {
                const desc = event.description
                  ? JSON.parse(event.description)
                  : null;
                // Merge metadata into the expanded view if available
                const detail = {
                  event_type: event.event_type,
                  status: event.status,
                  occurred_at: event.occurred_at,
                  ...(desc ?? {}),
                  ...(event.metadata ?? {}),
                };
                return JSON.stringify(detail, null, 2);
              } catch {
                return event.description ?? JSON.stringify(event, null, 2);
              }
            })()}
          </pre>
        )}
      </div>

      {/* Timestamp */}
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        <span
          className="text-[11px] tabular-nums text-muted-foreground/60"
          title={new Date(event.occurred_at).toLocaleString()}
        >
          {formatTimestamp(event.occurred_at)}
        </span>
      </div>
    </div>
  );
}
