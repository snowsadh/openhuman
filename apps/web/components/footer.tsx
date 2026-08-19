import Link from "next/link";

import { Logo } from "@/components/logo";

export function Footer() {
  return (
    <footer className="w-full border-t border-border/40 bg-[#1a1717]">
      <div className="mx-auto max-w-7xl px-6 py-16">
        <div className="flex flex-col items-center gap-8 sm:flex-row sm:justify-between">
          <Link
            href="/"
            className="flex items-center gap-1.5 text-white no-underline"
          >
            <Logo className="h-7 w-7 text-white" />
            <span className="text-lg font-medium">OpenHuman</span>
          </Link>

          <p className="text-sm text-white/50">
            Built with{" "}
            <span role="img" aria-label="love">
              ❤️
            </span>{" "}
            for the Cognee hackathon
          </p>
        </div>

        <div className="mt-12 border-t border-white/10 pt-8">
          <p className="text-center text-sm text-white/30">
            &copy; 2026 OpenHuman. All rights reserved. Built for the Cognee
            hackathon.
          </p>
        </div>
      </div>
    </footer>
  );
}
