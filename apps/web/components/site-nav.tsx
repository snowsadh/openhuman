"use client";

import Link from "next/link";
import { useIsSignedIn } from "@/hooks/use-auth";

import CardNav from "@/components/CardNav";
import { Logo } from "@/components/logo";

export function SiteNav() {
  const { isSignedIn, isLoaded } = useIsSignedIn();

  return (
    <CardNav
      logo={
        <Link
          href="/"
          className="flex items-center gap-1.5 text-white no-underline"
        >
          <Logo className="h-7 w-7 text-white" />
          OpenHuman
        </Link>
      }
      items={[
        {
          label: "Product",
          bgColor: "#3e4229",
          textColor: "#ffffff",
          links: [
            { label: "Features", href: "#", ariaLabel: "Features" },
            { label: "Changelog", href: "#", ariaLabel: "Changelog" },
          ],
        },
        {
          label: "Resources",
          bgColor: "#656b37",
          textColor: "#ffffff",
          links: [
            { label: "Docs", href: "#", ariaLabel: "Documentation" },
            {
              label: "GitHub",
              href: "https://github.com/openhuman/openhuman",
              ariaLabel: "GitHub",
            },
          ],
        },
        {
          label: "Company",
          bgColor: "#1a1717",
          textColor: "#e8ecd0",
          links: [
            { label: "About", href: "#", ariaLabel: "About" },
            { label: "Blog", href: "#", ariaLabel: "Blog" },
          ],
        },
      ]}
      baseColor="#1a1717"
      menuColor="#e8ecd0"
      buttonBgColor="#ffffff"
      buttonTextColor="#1a1717"
      ctaLabel={isLoaded && isSignedIn ? "Dashboard" : "Get Started"}
      ctaHref={isLoaded && isSignedIn ? "/dashboard" : "/sign-up"}
    />
  );
}
