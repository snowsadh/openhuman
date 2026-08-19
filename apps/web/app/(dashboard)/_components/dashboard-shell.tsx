"use client";

import { DashboardSidebar } from "@/app/(dashboard)/_components/dashboard-sidebar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-svh bg-background-app">
      <SidebarProvider>
        <DashboardSidebar />
        <SidebarInset className="bg-background-app">
          <div className="flex flex-1 flex-col">{children}</div>
        </SidebarInset>
      </SidebarProvider>
    </div>
  );
}
