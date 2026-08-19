"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3, Pause, Play, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  getSchedulesListSchedulesRouteQueryKey,
  schedulesListScheduleRunsRoute,
  useSchedulesCreateScheduleRoute,
  useSchedulesDeleteScheduleRoute,
  useSchedulesListSchedulesRoute,
  useSchedulesRunScheduleRoute,
  useSchedulesUpdateScheduleRoute,
} from "@repo/api-client";
import type { ScheduleResponse } from "@repo/api-client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

type Assignment = { platform: string; channel_id: string; channel_name?: string | null };

export function EmployeeAutomations({
  orgId,
  employeeId,
  duties,
  assignments,
  employeeStatus,
}: {
  orgId: string;
  employeeId: string;
  duties: string[];
  assignments: Assignment[];
  employeeStatus: string;
}) {
  const queryClient = useQueryClient();
  const { data: schedules = [], isLoading } = useSchedulesListSchedulesRoute(orgId, employeeId);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [cron, setCron] = useState("0 9 * * 1-5");
  const [timezone, setTimezone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [destination, setDestination] = useState("");
  const [selectedSchedule, setSelectedSchedule] = useState<string | null>(null);

  const refresh = () => queryClient.invalidateQueries({
    queryKey: getSchedulesListSchedulesRouteQueryKey(orgId, employeeId),
  });
  const create = useSchedulesCreateScheduleRoute({ mutation: { onSuccess: () => {
    toast.success("Automation scheduled");
    setName("");
    setPrompt("");
    void refresh();
  }, onError: (error) => toast.error(String(error)) } });
  const update = useSchedulesUpdateScheduleRoute({ mutation: { onSuccess: () => void refresh(), onError: (error) => toast.error(String(error)) } });
  const remove = useSchedulesDeleteScheduleRoute({ mutation: { onSuccess: () => void refresh(), onError: (error) => toast.error(String(error)) } });
  const run = useSchedulesRunScheduleRoute({ mutation: {
    onSuccess: () => toast.success("Run queued"),
    onError: (error) => toast.error(String(error)),
  } });
  const { data: recentRuns = [] } = useQuery({
    queryKey: ["schedule-runs", orgId, employeeId, selectedSchedule],
    queryFn: ({ signal }) => schedulesListScheduleRunsRoute(orgId, employeeId, selectedSchedule!, undefined, undefined, signal),
    enabled: Boolean(selectedSchedule),
  });

  const selectedDestination = useMemo(
    () => assignments.find((item) => `${item.platform}:${item.channel_id}` === destination),
    [assignments, destination],
  );

  const submit = () => {
    if (!name.trim() || !prompt.trim() || !selectedDestination) {
      toast.error("Name, instructions, and an assigned channel are required");
      return;
    }
    create.mutate({ orgId, empId: employeeId, data: {
      name: name.trim(),
      prompt: prompt.trim(),
      cron_expression: cron.trim(),
      timezone,
      platform: selectedDestination.platform as "slack" | "discord",
      channel_id: selectedDestination.channel_id,
    } });
  };

  const applyDuty = (duty: string) => {
    setName(duty.length > 60 ? `${duty.slice(0, 57)}...` : duty);
    setPrompt(duty);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold">Automations</h3>
            <p className="text-sm text-muted-foreground">Recurring duties run in fresh, isolated employee sessions.</p>
          </div>
          <Clock3 className="size-5 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {duties.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {duties.map((duty) => (
              <Button key={duty} type="button" size="sm" variant="outline" onClick={() => applyDuty(duty)}>
                <Plus className="size-3.5" /> Use duty
              </Button>
            ))}
          </div>
        )}
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1.5"><Label>Name</Label><Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Weekday hiring summary" /></div>
          <div className="space-y-1.5"><Label>Destination</Label>
            <Select value={destination} onValueChange={(value) => setDestination(value ?? "")}>
              <SelectTrigger><SelectValue placeholder="Assigned Slack or Discord channel" /></SelectTrigger>
              <SelectContent>{assignments.map((item) => (
                <SelectItem key={`${item.platform}:${item.channel_id}`} value={`${item.platform}:${item.channel_id}`}>
                  {item.platform} · {item.channel_name || item.channel_id}
                </SelectItem>
              ))}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5"><Label>Cron expression</Label><Input value={cron} onChange={(event) => setCron(event.target.value)} /></div>
          <div className="space-y-1.5"><Label>Timezone</Label><Input value={timezone} onChange={(event) => setTimezone(event.target.value)} /></div>
        </div>
        <div className="space-y-1.5"><Label>Self-contained instructions</Label><Textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={4} placeholder="Explain exactly what the employee should do and what a useful result looks like." /></div>
        <Button type="button" onClick={submit} disabled={create.isPending || assignments.length === 0}>
          <Plus className="size-4" /> Create automation
        </Button>
        {assignments.length === 0 && <p className="text-sm text-amber-600">Assign this employee to a Slack or Discord channel before scheduling work.</p>}

        <div className="space-y-2">
          {isLoading && <p className="text-sm text-muted-foreground">Loading automations…</p>}
          {schedules.map((item: ScheduleResponse) => (
            <div key={item.id} className="rounded-lg border p-3">
              <div className="flex items-start justify-between gap-3">
                <button type="button" className="min-w-0 text-left" onClick={() => setSelectedSchedule(selectedSchedule === item.id ? null : item.id)}>
                  <div className="flex items-center gap-2"><span className="font-medium">{item.name}</span><Badge variant="outline">{item.status}</Badge></div>
                  <p className="mt-1 text-xs text-muted-foreground">{item.cron_expression} · {item.timezone} · next {new Date(item.next_run_at).toLocaleString()}</p>
                  {item.last_error && <p className="mt-1 text-xs text-destructive">{item.last_error}</p>}
                </button>
                <div className="flex shrink-0 gap-1">
                  <Button size="icon" variant="ghost" disabled={employeeStatus !== "active" || run.isPending} onClick={() => run.mutate({ orgId, empId: employeeId, scheduleId: item.id })}><Play className="size-4" /></Button>
                  <Button size="icon" variant="ghost" onClick={() => update.mutate({ orgId, empId: employeeId, scheduleId: item.id, data: { status: item.status === "active" ? "paused" : "active" } })}><Pause className="size-4" /></Button>
                  <Button size="icon" variant="ghost" onClick={() => remove.mutate({ orgId, empId: employeeId, scheduleId: item.id })}><Trash2 className="size-4" /></Button>
                </div>
              </div>
              {selectedSchedule === item.id && (
                <div className="mt-3 border-t pt-2 text-xs text-muted-foreground">
                  {recentRuns.length === 0 ? "No runs yet." : recentRuns.slice(0, 5).map((recent) => (
                    <div key={recent.id} className="flex justify-between py-1"><span>{recent.status} · delivery {recent.delivery_status || "pending"}</span><span>{recent.scheduled_for ? new Date(recent.scheduled_for).toLocaleString() : "manual"}</span></div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
