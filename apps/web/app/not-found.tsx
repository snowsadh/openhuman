"use client";

import Link from "next/link";
import { FlowerDivider } from "@/components/flower-divider";
import { SiteNav } from "@/components/site-nav";
import { ArrowRight } from "@/components/ui/button-arrow";

export default function NotFound() {
  return (
    <>
      <SiteNav />
      <main className="flex min-h-screen flex-col items-center justify-center px-6">
        <FlowerDivider className="w-64" />
        <h1 className="mt-3 text-center text-8xl font-base tracking-tight text-foreground">
          Page not found
        </h1>
        <p className="mt-4 max-w-lg text-center text-lg leading-relaxed text-muted-foreground">
          The page you're looking for doesn't exist or was moved.
        </p>
        <div className="mt-10">
          <Link
            href="/"
            className="group/button inline-flex items-center gap-3 rounded-lg bg-primary px-10 py-5 text-lg font-medium text-primary-foreground shadow-lg shadow-foreground/10 no-underline"
          >
            Go home
            <ArrowRight size={16} />
          </Link>
        </div>
      </main>
    </>
  );
}
