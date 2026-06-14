import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { AuthControls } from "@/components/AuthControls";

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
          <header className="border-b border-gray-200 bg-white px-6 py-4">
            <nav className="mx-auto flex max-w-6xl items-center gap-6">
              <a href="/" className="text-xl font-bold tracking-tight text-indigo-600">
                MarketTrace
              </a>
              <a
                href="/events"
                className="text-sm font-medium text-gray-600 hover:text-gray-900"
              >
                Events
              </a>
              <a
                href="/stats"
                className="text-sm font-medium text-gray-600 hover:text-gray-900"
              >
                Stats
              </a>
              <div className="ml-auto">
                <AuthControls />
              </div>
            </nav>
          </header>
          <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
