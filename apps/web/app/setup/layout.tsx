import { SetupLayoutShell } from "./_components/setup-layout-shell";

export default function SetupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <SetupLayoutShell>{children}</SetupLayoutShell>;
}
