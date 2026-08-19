"use client";

import type { EmployeeDisplay } from "@/types/employee";
import { getStatusConfig } from "@/types/employee";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { BrandLogo } from "@/components/brand-logos";

interface EmployeeCardProps {
  employee: EmployeeDisplay;
  className?: string;
  onClick?: () => void;
  selected?: boolean;
}

export function EmployeeCard({
  employee,
  className,
  onClick,
  selected,
}: EmployeeCardProps) {
  const isInteractive = Boolean(onClick);
  const statusConfig = getStatusConfig(employee.status);
  const isWorking =
    employee.status === "active" || employee.status === "training";

  return (
    <Card
      className={cn(
        "group/employee",
        isInteractive && "cursor-pointer transition-shadow hover:shadow-md",
        selected && "ring-2 ring-primary",
        className,
      )}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter") onClick();
            }
          : undefined
      }
      role={isInteractive ? "button" : undefined}
      tabIndex={isInteractive ? 0 : undefined}
    >
      <CardContent className="flex flex-col h-full">
        {/* Top row: status dot + name + role */}
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "inline-block size-2 shrink-0 rounded-full",
              statusConfig.dotColor,
            )}
          />
          <h3 className="truncate text-base font-semibold text-foreground">
            {employee.name}
          </h3>
        </div>

        <p className="mt-0.5 text-sm text-muted-foreground">{employee.role}</p>

        {/* Working / Idle badge + specialization */}
        <div className="mt-2 flex items-center gap-2 text-xs">
          {employee.specialization && (
            <span className="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 font-medium text-muted-foreground">
              {employee.specialization}
            </span>
          )}
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium text-xs",
              isWorking
                ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
            )}
          >
            <span
              className={cn(
                "size-1.5 rounded-full",
                isWorking ? "bg-green-500" : "bg-amber-400",
              )}
            />
            {statusConfig.label}
          </span>
        </div>

        {/* Current task — truncated */}
        {employee.currentTask && (
          <div className="mt-2.5 flex items-start gap-1.5">
            <span className="mt-0.5 shrink-0 text-[10px] text-muted-foreground/60 select-none">
              ▸
            </span>
            <p className="text-xs text-muted-foreground line-clamp-1 leading-relaxed">
              {employee.currentTask}
            </p>
          </div>
        )}

        {/* Spacer to push MCP logos to the bottom */}
        <div className="flex-1" />

        {/* MCP logos row */}
        {employee.mcpConnectionSlugs.length > 0 && (
          <div className="mt-3 flex items-center gap-1.5 pt-2 border-t border-muted/50">
            <span className="text-[10px] text-muted-foreground/50 shrink-0">
              MCPs
            </span>
            <div className="flex items-center gap-1">
              {employee.mcpConnectionSlugs.map((slug) => (
                <span
                  key={slug}
                  className="flex size-5 items-center justify-center rounded bg-muted/30"
                  title={slug}
                >
                  <BrandLogo slug={slug} className="size-3.5" />
                </span>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
