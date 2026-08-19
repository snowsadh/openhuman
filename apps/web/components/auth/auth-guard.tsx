"use client";

import Link from "next/link";
import { useIsSignedIn } from "@/hooks/use-auth";
import { ArrowRightIcon } from "lucide-react";

import { Spinner } from "@/components/ui/spinner";

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const { isSignedIn, isLoaded } = useIsSignedIn();

  if (!isLoaded) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }

  if (isSignedIn) {
    return (
      <div className="flex h-screen items-center justify-center bg-background-app">
        <div className="flex flex-col items-center gap-4 text-center">
          <p className="text-sm text-muted-foreground">
            You&apos;re already signed in.
          </p>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Go to dashboard
            <ArrowRightIcon className="size-3.5" />
          </Link>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
