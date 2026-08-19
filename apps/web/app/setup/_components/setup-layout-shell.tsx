"use client";

import Link from "next/link";
import { handleSignOut } from "@/hooks/use-auth";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { useOrgStore } from "@/stores/org";

export function SetupLayoutShell({ children }: { children: React.ReactNode }) {
  const clearOrg = useOrgStore((s) => s.clearOrg);

  const handleLogout = () => {
    clearOrg();
    handleSignOut("/");
  };

  return (
    <div className="relative flex min-h-svh flex-col bg-background-app">
      <div className="absolute right-4 top-4 flex items-center gap-3">
        <Button variant="outline" size="sm" onClick={handleLogout}>
          Sign out
        </Button>
      </div>

      <div className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg space-y-8">
          <Link
            href="/"
            className="flex items-center justify-center gap-1.5 no-underline"
          >
            <Logo className="h-6 w-6" />
            <span className="text-lg font-semibold tracking-tight text-foreground">
              OpenHuman
            </span>
          </Link>
          {children}
        </div>
      </div>
    </div>
  );
}
