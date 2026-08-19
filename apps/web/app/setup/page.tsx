"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useIsSignedIn } from "@/hooks/use-auth";
import {
  useOrganizationsCreateOrganization,
  useOrganizationsListOrganizations,
  useOrganizationsUpdateOrganization,
} from "@repo/api-client";
import { useAuthUpdateMe } from "@repo/api-client";
import { useOrgStore } from "@/stores/org";
import { Spinner } from "@/components/ui/spinner";
import { KnowledgeUpload } from "./_components/knowledge-upload";
import { OrgSetupForm } from "./_components/org-setup-form";
import type { OrgSetupFormData } from "./_components/org-setup-form";

type Step = "org-details" | "knowledge-upload";

export default function SetupPage() {
  const router = useRouter();
  const { isSignedIn, isLoaded } = useIsSignedIn();
  const setOrg = useOrgStore((s) => s.setOrg);
  const [step, setStep] = useState<Step>("org-details");
  const [orgId, setOrgId] = useState<string | null>(null);
  const [orgName, setOrgName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createOrgMutation = useOrganizationsCreateOrganization();
  const updateOrgMutation = useOrganizationsUpdateOrganization();
  const updateUserMutation = useAuthUpdateMe();

  const { data: orgs, isLoading: orgsLoading } = useOrganizationsListOrganizations({
    query: { enabled: isLoaded && isSignedIn },
  });

  const existingOrg = useMemo(() => orgs?.[0] ?? null, [orgs]);
  const shouldGoToDashboard = !orgsLoading && !!existingOrg;

  useEffect(() => {
    if (!shouldGoToDashboard || !existingOrg) {
      if (shouldGoToDashboard) {
        router.replace("/dashboard");
      }
      return;
    }

    setOrg(existingOrg.id, existingOrg.name);
    router.replace("/dashboard");
  }, [existingOrg, router, setOrg, shouldGoToDashboard]);

  const finishSetup = useCallback(
    async (finalOrgId: string, finalOrgName: string) => {
      await updateUserMutation.mutateAsync({
        data: { onboarding_completed: true },
      });

      setOrg(finalOrgId, finalOrgName);
      router.replace("/dashboard");
    },
    [router, setOrg, updateUserMutation],
  );

  const handleSubmit = useCallback(
    async (data: OrgSetupFormData) => {
      setIsSubmitting(true);
      setError(null);

      try {
        const org = existingOrg
          ? await updateOrgMutation.mutateAsync({
              orgId: existingOrg.id,
              data: {
                name: data.name,
                description: data.description || undefined,
                what_it_does: data.what_it_does || undefined,
                website_url: data.website_url || undefined,
              },
            })
          : await createOrgMutation.mutateAsync({
              data: {
                name: data.name,
                description: data.description || undefined,
                what_it_does: data.what_it_does || undefined,
                website_url: data.website_url || undefined,
              },
            });

        setOrgId(org.id);
        setOrgName(org.name);
        setStep("knowledge-upload");
      } catch {
        setError("Failed to set up your organization. Please try again.");
      } finally {
        setIsSubmitting(false);
      }
    },
    [
      createOrgMutation,
      existingOrg,
      updateOrgMutation,
    ],
  );

  if (!isLoaded || orgsLoading) {
    return (
      <div className="flex justify-center">
        <Spinner />
      </div>
    );
  }

  if (shouldGoToDashboard) {
    return null;
  }

  return (
    <div className="space-y-6">
      {step === "org-details" ? (
        <>
          <div className="space-y-1.5 text-center">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              Set up your workspace
            </h1>
            <p className="text-sm text-muted-foreground">
              Add your organization details to get started
            </p>
          </div>

          <OrgSetupForm
            onSubmit={handleSubmit}
            isSubmitting={isSubmitting}
            error={error}
          />
        </>
      ) : orgId ? (
        <>
          <div className="space-y-1.5 text-center">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              Add your knowledge base
            </h1>
            <p className="text-sm text-muted-foreground">
              Upload company docs now, or skip and do it later from the dashboard.
            </p>
          </div>

          <KnowledgeUpload
            orgId={orgId}
            onComplete={() => void finishSetup(orgId, orgName)}
            onSkip={() => void finishSetup(orgId, orgName)}
          />
        </>
      ) : null}
    </div>
  );
}
