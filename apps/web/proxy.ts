// Deploy check: verify Railway auto-deploy on push (web).
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PROTECTED_PATHS = ["/dashboard", "/onboard", "/setup", "/organization", "/activity", "/storage", "/settings"];

export default function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Redirect legacy auth routes
  if (pathname === "/login") return NextResponse.redirect(new URL("/sign-in", req.url));
  if (pathname === "/signup") return NextResponse.redirect(new URL("/sign-up", req.url));

  // For protected routes, check for the auth cookie (we can't read localStorage in middleware)
  // Auth guarding is done client-side via useIsSignedIn; middleware just provides a basic redirect
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
