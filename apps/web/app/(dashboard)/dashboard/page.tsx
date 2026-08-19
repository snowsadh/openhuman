"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PlusIcon, SearchIcon, UsersIcon } from "lucide-react";

import { useEmployeesListEmployeesRoute } from "@repo/api-client";
import { toast } from "sonner";
import { useOrgStore } from "@/stores/org";
import { apiToEmployeeDisplay } from "@/types/employee";
import { EmployeeCard } from "@/components/employee-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

export default function DashboardPage() {
  const router = useRouter();
  const orgId = useOrgStore((s) => s.orgId);
  const [search, setSearch] = useState("");
  const searchParams = useSearchParams();

  useEffect(() => {
    const slack = searchParams.get("slack");
    if (slack === "connected") {
      toast.success("Slack workspace connected successfully!");
    } else if (slack === "error") {
      const reason = searchParams.get("reason") || "unknown error";
      toast.error(`Slack connection failed: ${reason}`);
    }
    if (slack) {
      const next = new URL(window.location.href);
      next.searchParams.delete("slack");
      next.searchParams.delete("reason");
      window.history.replaceState({}, "", next.toString());
    }
  }, [searchParams]);

  const enabled = !!orgId;
  const {
    data: apiEmployees,
    isLoading,
    isError,
    refetch,
  } = useEmployeesListEmployeesRoute(orgId ?? "", {
    query: { enabled },
  });

  const employees = useMemo(
    () => (apiEmployees ?? []).map(apiToEmployeeDisplay),
    [apiEmployees],
  );

  const filtered = useMemo(() => {
    if (!search.trim()) return employees;
    const q = search.toLowerCase();
    return employees.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.role.toLowerCase().includes(q) ||
        e.specialization.toLowerCase().includes(q),
    );
  }, [employees, search]);

  return (
    <div className="flex flex-col gap-6 px-6 py-6">
      <div className="flex flex-col gap-1">
        <p className="text-2xl font-semibold tracking-tight text-foreground">
          Welcome back
        </p>
      </div>
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5 shrink-0">
          <UsersIcon className="size-5 text-muted-foreground" />
          <h1 className="text-lg font-semibold tracking-tight text-foreground">
            Team
          </h1>
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            {employees.length}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search agents…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-56 h-9 pl-8"
            />
          </div>
          <Button size="lg" onClick={() => router.push("/onboard")}>
            <PlusIcon />
            Add Employee
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center justify-center py-24">
          <p className="text-sm text-muted-foreground">
            Failed to load employees.
          </p>
          <Button variant="link" onClick={() => refetch()} className="mt-2">
            Try again
          </Button>
        </div>
      ) : filtered.length === 0 && employees.length > 0 ? (
        <div className="flex flex-col items-center justify-center py-24">
          <SearchIcon className="size-10 text-muted-foreground/40" />
          <p className="mt-3 text-sm text-muted-foreground">
            No agents match your search.
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24">
          <UsersIcon className="size-10 text-muted-foreground/40" />
          <p className="mt-3 text-sm text-muted-foreground">
            No AI agents deployed yet.
          </p>
          <p className="text-xs text-muted-foreground/60">
            Click &ldquo;Add Employee&rdquo; to deploy your first agent.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((employee) => (
            <EmployeeCard
              key={employee.id}
              employee={employee}
              onClick={() => router.push(`/dashboard/${employee.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
