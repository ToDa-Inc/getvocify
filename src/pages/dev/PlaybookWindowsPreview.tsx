import { useEffect, useState } from "react";
import { DashboardThemeProvider } from "@/components/ThemeProvider";
import { CompanyWindow } from "@/features/playbooks/components/home/CompanyWindow";
import { FunnelWindow } from "@/features/playbooks/components/home/FunnelWindow";
import { PlaybookHomeView } from "@/features/playbooks/components/home/PlaybookHome";
import type { HomeType } from "@/features/playbooks/components/home/FunnelBlock";
import type { Intake } from "@/features/playbooks/hooks/useIntake";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/**
 * Development only: the real Playbook windows (funnel, other calls, company) driven against a fake API held in memory, so the
 * whole flow can be clicked through without a login. /__preview/playbook-windows. Nothing reaches a server.
 */

type Row = { key: string; label: string; stage: string; goal: string | null; recognize: string | null; position: number; step_count: number; status: string };
const db: { types: Row[]; knowledge: Record<string, unknown>; updated: string | null; filled: Set<string> } = { types: [], knowledge: {}, updated: null, filled: new Set() };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const slug = (label: string) => label.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "tipo";
const view = () => ({ types: db.types.map((t, i) => ({ ...t, position: i + 1, step_count: db.filled.has(t.key) ? 4 : 0 })) });

function install() {
  const real = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    await new Promise((r) => setTimeout(r, 350));
    if (url.includes("/sales-process") && !url.includes("/members")) {
      if (method === "PUT") {
        db.types = (body.types as Row[]).map((t) => ({ ...t, key: t.key ?? slug(t.label), goal: t.goal ?? null, recognize: t.recognize ?? null, position: 0, step_count: 0, status: "missing" }));
      }
      return json(view());
    }
    if (url.includes("/playbooks/company/fill")) {
      db.knowledge = { notes: "Vocify es una plataforma de IA para equipos de ventas.", pricing: "Desde 49 € al mes por usuario.", icp: "Equipos de 5 a 50 comerciales.", competitors: [{ name: "Gong", how_to_talk: "más caro y sin ayuda en directo" }] };
      db.updated = new Date().toISOString();
      return json({ knowledge: db.knowledge, updated_at: db.updated, sections: [], filled: ["notes"], summary: "" });
    }
    if (url.includes("/playbooks/company")) {
      if (method === "PUT") {
        db.knowledge = body.knowledge;
        db.updated = new Date().toISOString();
      }
      return json({ knowledge: db.knowledge, updated_at: db.updated, sections: [] });
    }
    const structure = url.match(/\/playbooks\/([^/]+)\/structure/);
    if (structure) {
      if (String(body?.payload ?? "").trim().length < 20) return json({ sales_motion_key: structure[1], steps: [], objections: [], qualification: [], reason: "no_process", fallback: false, source: null });
      return json({ sales_motion_key: structure[1], steps: [{ label: "Apertura", criterion: "Se presenta y pide un minuto." }, { label: "Motivo", criterion: "Dice por qué llama." }], objections: [], qualification: [], reason: null, fallback: false, source: { id: "src-1" } });
    }
    if (/\/playbooks\/[^/]+\/editor/.test(url)) return json({ updated_at: null, steps: [], objections: [], qualification: [] });
    const draft = url.match(/\/playbooks\/([^/]+)\/draft/);
    if (draft) {
      db.filled.add(decodeURIComponent(draft[1]));
      return json({});
    }
    if (url.includes("/api/")) return json({ detail: "not in the preview" }, 404);
    return real(input, init);
  };
  return () => {
    window.fetch = real;
  };
}

const intake = { submit: async () => undefined, submitMany: async () => undefined, notice: null } as unknown as Intake;

export default function PlaybookWindowsPreview() {
  const [ready, setReady] = useState(false);
  const [open, setOpen] = useState<"funnel" | "other" | "company" | null>(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const undo = install();
    setReady(true);
    return undo;
  }, []);
  const types: HomeType[] = db.types.map((t) => ({ key: t.key, label: t.label, goal: t.goal, description: t.recognize, stage: t.stage, state: db.filled.has(t.key) ? "unpublished" : "empty" }));
  if (!ready) return null;
  return (
    <DashboardThemeProvider>
      <div className="dashboard-shell min-h-dvh bg-background p-4 md:p-10" data-version={version}>
        <main className="mx-auto max-w-5xl space-y-8">
          <h1 className={THEME_TOKENS.typography.pageTitle}>Playbook</h1>
          <PlaybookHomeView
            types={types}
            areas={[]}
            canEdit
            onCreateFunnel={() => setOpen("funnel")}
            onOpenType={() => setOpen("funnel")}
            onCreateCompany={() => setOpen("company")}
            onOpenCompany={() => setOpen("company")}
            onCreateOther={() => setOpen("other")}
          />
        </main>
        <FunnelWindow
          open={open === "funnel" || open === "other"}
          onOpenChange={(next) => !next && setOpen(null)}
          kind={open === "other" ? "other" : "funnel"}
          types={types}
          intake={intake}
          assistantOn={false}
          onChanged={() => setVersion((v) => v + 1)}
        />
        <CompanyWindow open={open === "company"} onOpenChange={(next) => !next && setOpen(null)} canEdit />
      </div>
    </DashboardThemeProvider>
  );
}
