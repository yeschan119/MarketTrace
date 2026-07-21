import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { CatMascot } from "@/components/CatMascot";
import { SiteHeader } from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: "MarketTrace",
  description: "Market event analysis and tracking dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <Providers>
          <SiteHeader />
          <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
          <CatMascot
            name="냉이"
            src="/assets/cat-mascot-sprite.png"
            variant="naengi"
          />
          <CatMascot
            name="꿍이"
            src="/assets/koongi-mascot-sprite.png"
            variant="koongi"
          />
        </Providers>
      </body>
    </html>
  );
}
