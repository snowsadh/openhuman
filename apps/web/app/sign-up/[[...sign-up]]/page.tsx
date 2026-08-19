import Image from "next/image";
import Link from "next/link";
import { ArrowLeftIcon } from "lucide-react";

import { AuthGuard } from "@/components/auth/auth-guard";
import { SignUpForm } from "@/components/auth/sign-up-form";
import { Logo } from "@/components/logo";

export default function SignUpPage() {
  return (
    <AuthGuard>
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-2">
      {/* Left — decorative image */}
      <div
        className="relative hidden overflow-hidden bg-[#1a1717] lg:block"
        style={{ viewTransitionName: "auth-image" }}
      >
        <Image
          src="/auth-signup.jpg"
          alt=""
          fill
          className="object-cover opacity-80"
          sizes="50vw"
          priority
        />
        {/* Gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-[#1a1717] via-[#1a1717]/20 to-transparent" />
        {/* Branding */}
        <div className="absolute bottom-8 left-8 right-8">
          <Logo className="h-8 w-8 text-white/90" />
          <p className="mt-2 text-xs font-medium tracking-wider text-white/50">
            OpenHuman
          </p>
        </div>
      </div>

      {/* Right — form */}
      <div
        className="relative flex items-center justify-center bg-background-app px-4 py-12 md:px-8"
        style={{ viewTransitionName: "auth-form" }}
      >
        <Link
          href="/"
          className="absolute left-4 top-4 inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground md:left-8 md:top-8"
        >
          <ArrowLeftIcon className="size-3.5" />
          Back
        </Link>
        <SignUpForm />
      </div>
    </div>
    </AuthGuard>
  );
}
