"use client";

import { Suspense, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useIsSignedIn } from "@/hooks/use-auth";
import { useOrganizationsListOrganizations } from "@repo/api-client";
import { useOrgStore } from "@/stores/org";
import { DashboardShell } from "@/app/(dashboard)/_components/dashboard-shell";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

function OrgInitializer({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const orgId = useOrgStore((s) => s.orgId);
  const orgName = useOrgStore((s) => s.orgName);
  const setOrg = useOrgStore((s) => s.setOrg);
  const clearOrg = useOrgStore((s) => s.clearOrg);
  const { isSignedIn, isLoaded } = useIsSignedIn();

  const {
    data: orgs,
    isLoading: orgsLoading,
    isError,
    refetch,
  } = useOrganizationsListOrganizations({
    query: { enabled: isLoaded && isSignedIn },
  });

  useEffect(() => {
    if (!isLoaded || orgsLoading) return;

    const firstOrg = orgs?.[0] ?? null;

    if (!firstOrg) {
      clearOrg();
      router.replace("/setup");
      return;
    }

    setOrg(firstOrg.id, firstOrg.name);
  }, [clearOrg, isLoaded, orgs, orgsLoading, router, setOrg]);

  const firstOrg = orgs?.[0] ?? null;
  const orgReady =
    !!firstOrg && orgId === firstOrg.id && orgName === firstOrg.name;

  if (isError) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-center">
          <p className="text-sm text-muted-foreground">
            Unable to load your workspace.
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      </div>
    );
  }

  if (!isLoaded || orgsLoading || !orgReady) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return <>{children}</>;
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <DashboardShell>
      <Suspense fallback={null}>
        <OrgInitializer>{children}</OrgInitializer>
      </Suspense>
    </DashboardShell>
  );
}
