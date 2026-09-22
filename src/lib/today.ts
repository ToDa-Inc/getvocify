/** How Hoy reads GET /today. A partial source is not "nothing urgent". */

export type TodayItem = {
  type: string;
  dedupe_key: string | null;
  contact_id?: string | null;
  reason: string;
  remote_id?: string | null;
  origins: string[];
  supporting: string[];
  id?: string | null;
  version?: number | null;
  status?: string | null;
  undo_deadline?: string | null;
};

export type TodayView = {
  items: TodayItem[];
  pulse: number | null;
  folded_count: number;
  generated_at: string;
  coverage: Record<string, string>;
};

export type TodaySurface =
  | { kind: "loading" }
  | { kind: "error"; title: string }
  | { kind: "connect"; title: string; action: string | null; detail: string | null }
  | { kind: "no-activity"; title: string }
  | { kind: "incomplete"; title: string; generatedAt: string }
  | { kind: "clear"; title: string }
  | { kind: "list"; items: TodayItem[]; note: string | null; stale: boolean; generatedAt: string; pulse: number | null };

function sourcesComplete(coverage: Record<string, string>): boolean {
  const values = Object.values(coverage);
  return values.length > 0 && values.every((value) => value === "complete");
}

export function todaySurface(input: {
  data?: TodayView | null;
  errorStatus?: number | null;
  isLoading: boolean;
  connected: boolean;
  role: string;
}): TodaySurface {
  if (input.data) {
    const incomplete = !sourcesComplete(input.data.coverage);
    if (input.data.items.length > 0) {
      return {
        kind: "list",
        items: input.data.items,
        note: incomplete || input.errorStatus ? "Información incompleta" : null,
        stale: Boolean(input.errorStatus),
        generatedAt: input.data.generated_at,
        pulse: input.data.pulse,
      };
    }
    if (!input.connected) {
      const canConnect = input.role === "owner" || input.role === "admin";
      return {
        kind: "connect",
        title: "Conecta tu CRM para preparar tu día",
        action: canConnect ? "Conectar CRM" : null,
        detail: canConnect ? null : "Tu administrador tiene que conectar el CRM.",
      };
    }
    if (incomplete || input.errorStatus) {
      return { kind: "incomplete", title: "Información incompleta", generatedAt: input.data.generated_at };
    }
    return { kind: "clear", title: "Nada urgente hoy. Buen momento para prospectar" };
  }
  if (input.isLoading) return { kind: "loading" };
  if (input.errorStatus) return { kind: "error", title: "No se pudo preparar el día" };
  if (!input.connected) {
    const canConnect = input.role === "owner" || input.role === "admin";
    return {
      kind: "connect",
      title: "Conecta tu CRM para preparar tu día",
      action: canConnect ? "Conectar CRM" : null,
      detail: canConnect ? null : "Tu administrador tiene que conectar el CRM.",
    };
  }
  return { kind: "no-activity", title: "Todavía no hay actividad registrada para preparar tu día" };
}

export function cardsAfterDismiss(server: TodayItem[], acted: TodayItem[], nowMs: number): TodayItem[] {
  const actedById = new Map(acted.filter((item) => item.id).map((item) => [item.id as string, item]));
  const undoable = (item: TodayItem) =>
    item.status === "dismissed" && item.undo_deadline != null && Date.parse(item.undo_deadline) >= nowMs;
  const merged = server.map((item) => {
    const next = item.id ? actedById.get(item.id) : undefined;
    return next && undoable(next) ? next : item;
  });
  const serverIds = new Set(server.map((item) => item.id).filter(Boolean));
  const extra = acted.filter((item) => item.id && !serverIds.has(item.id) && undoable(item));
  return [...merged, ...extra];
}
