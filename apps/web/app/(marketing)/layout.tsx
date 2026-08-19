import { Footer } from "@/components/footer";
import { SiteNav } from "@/components/site-nav";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <SiteNav />
      {children}
      <Footer />
    </>
  );
}
