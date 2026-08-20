import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { Toaster } from "sonner";
import { Providers } from "@/lib/providers";
import { CommandPaletteRoot } from "@/components/command-palette-root";
import { ErrorBoundary } from "@/components/error-boundary";

export const metadata: Metadata = {
  title: "AI Research Workspace",
  description: "Enterprise-grade AI research platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <Providers>
            <TooltipProvider delayDuration={150}>
              <Sidebar />
              <Topbar />
              <main className="md:pl-60">
                <div className="min-h-[calc(100vh-3.5rem)]">
                  <ErrorBoundary level="page">{children}</ErrorBoundary>
                </div>
              </main>
              <Toaster position="top-right" richColors closeButton />
            </TooltipProvider>
          </Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}
