"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { handleSignOut } from "@/hooks/use-auth";
import {
  Activity,
  BookOpen,
  Building2,
  HardDrive,
  LayoutDashboard,
  LogOut,
  Moon,
  Puzzle,
  Settings,
  Sun,
} from "lucide-react";

import { Logo } from "@/components/logo";
import { useOrgStore } from "@/stores/org";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

const NAV_ITEMS = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Activity", href: "/activity", icon: Activity },
  { label: "Storage", href: "/storage", icon: HardDrive },
  { label: "MCP Marketplace", href: "/mcp-marketplace", icon: Puzzle },
  { label: "Organization", href: "/organization", icon: Building2 },
  { label: "Documentation", href: "/docs", icon: BookOpen },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function DashboardSidebar() {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const clearOrg = useOrgStore((s) => s.clearOrg);

  return (
    <Sidebar>
      <SidebarHeader>
        <div className="flex items-center justify-between px-3 pt-2">
          <Link
            href="/"
            className="flex items-center gap-1.5 text-lg font-semibold tracking-tight text-sidebar-foreground no-underline group-data-[collapsible=icon]:hidden"
          >
            <span>Open</span>
            <Logo className="h-6 w-6 shrink-0 text-sidebar-foreground" />
            <span>Human</span>
          </Link>
          <button
            type="button"
            aria-label={theme === "dark" ? "Light mode" : "Dark mode"}
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="flex size-7 items-center justify-center rounded-md text-sidebar-foreground/60 hover:text-sidebar-foreground transition-colors"
          >
            <Sun className="hidden dark:block size-4" />
            <Moon className="block dark:hidden size-4" />
          </button>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className="gap-1">
              {NAV_ITEMS.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    isActive={pathname === item.href}
                    tooltip={item.label}
                    render={<Link href={item.href} />}
                  >
                    <item.icon />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Logout"
                  onClick={() => {
                    clearOrg();
                    handleSignOut("/");
                  }}
                >
                  <LogOut />
                  <span>Logout</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarFooter>
    </Sidebar>
  );
}
