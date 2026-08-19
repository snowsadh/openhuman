import type { Metadata } from "next";
import { hafferSans, hafferMono } from "@/lib/fonts";
import { Providers } from "@/components/providers";
import { cn } from "@/lib/utils";
import "./globals.css";

export const metadata: Metadata = {
  title: "OpenHuman",
  description: "OpenHuman — AI-powered human simulation platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(
        "h-full",
        "antialiased",
        hafferSans.variable,
        hafferMono.variable,
      )}
    >
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
