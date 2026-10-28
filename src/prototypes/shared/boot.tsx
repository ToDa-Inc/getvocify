// Prototypes only: mounts a page as the dashboard would, on the local read-only API (prototypes/playbook-briefing/local_api.py,
// port 8888), with a stand-in session. Reads go through; the draft "saves" by answering with what was sent (nothing is
// stored); a call type's «Completar» / «Dile a Vocify» (/fill) runs the real model and saves nothing; every other write
// is refused here.
import type { ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { DashboardThemeProvider } from "@/components/ThemeProvider";
import { AuthProvider } from "@/features/auth";
import { LanguageProvider } from "@/lib/i18n";
import "@/index.css";
import "@/lib/theme/materials.css";

export function boot(path: string, page: ReactNode) {
  // A local stand-in for a session, so the page asks /auth/me (the local API answers as Vocify's owner and ignores it).
  const part = (value: object) => btoa(JSON.stringify(value)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
  localStorage.setItem("vocify_token", `${part({ alg: "none" })}.${part({ sub: "local", exp: Math.floor(Date.now() / 1000) + 86_400 })}.local`);
  const real = window.fetch.bind(window);
  // Drafts saved on the page, by call type, so a reload of the editor shows them (nothing reaches the database).
  const drafts = new Map<string, unknown>();
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const editor = url.match(/\/playbooks\/([^/?]+)\/editor(\?|$)/);
    if (method === "GET" && editor && !url.includes("live=true") && drafts.has(editor[1])) {
      return new Response(JSON.stringify(drafts.get(editor[1])), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (!url.includes("/api/v1/") || method === "GET" || url.includes("/conduct") || /\/playbooks\/(?!company\/)[^/]+\/fill$/.test(url) || url.endsWith("/playbooks/company/read"))
      return real(input, init);
    // The draft "saves": the same content back, as the API answers, and nothing is sent.
    if (method === "PUT" && url.endsWith("/draft")) {
      const doc = await real(url.replace(/\/draft$/, "/editor"), { headers: init?.headers }).then((r) => r.json());
      const body = JSON.parse(String(init?.body ?? "{}"));
      const key = url.match(/\/playbooks\/([^/]+)\/draft$/)?.[1];
      const saved = { ...doc, ...body, updated_at: new Date().toISOString() };
      if (key) drafts.set(key, saved);
      return new Response(JSON.stringify(saved), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    console.info("prototype: not sent", method, url);
    return new Response(JSON.stringify({ detail: { code: "local_read_only" } }), { status: 403, headers: { "Content-Type": "application/json" } });
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
  createRoot(document.getElementById("root")!).render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <LanguageProvider>
          <AuthProvider>
            <DashboardThemeProvider>
              <TooltipProvider delayDuration={200}>
                {page}
                <Toaster />
              </TooltipProvider>
            </DashboardThemeProvider>
          </AuthProvider>
        </LanguageProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
