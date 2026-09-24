/** How Hoy reads GET /today. A partial source is not "nothing urgent". */

import type { ProductTranslations } from "./product-catalog";

export type TodayItem = {
  type: string;
  dedupe_key: string | null;
  contact_id?: string | null;
  reason: string;
  contact_name?: string | null;
  company_name?: string | null;
  detail?: string | null;
  remote_id?: string | null;
  origins: string[];
  supporting: string[];
  open_url?: string | null;
  id?: string | null;
  version?: number | null;
  status?: string | null;
  undo_deadline?: string | null;
  last_action_request_id?: string | null;
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
  | { kind: "no-activity"; title: string; actions: readonly ["today_record", "open_contacts"] }
  | { kind: "incomplete"; title: string; generatedAt: string }
  | { kind: "clear"; title: string }
  | { kind: "list"; items: TodayItem[]; note: string | null; stale: boolean; generatedAt: string; pulse: number | null; foldedCount: number };

export type TodayCopy = Pick<
  ProductTranslations,
  | "today_incomplete"
  | "today_connect_title"
  | "connect_crm"
  | "today_connect_admin_detail"
  | "today_prepare_failed"
  | "today_clear"
  | "today_no_activity"
>;

function sourcesComplete(coverage: Record<string, string>): boolean {
  const values = Object.values(coverage);
  return values.length > 0 && values.every((value) => value === "complete");
}

export function todaySurface(
  input: {
    data?: TodayView | null;
    errorStatus?: number | null;
    isLoading: boolean;
    connected: boolean;
    role: string;
  },
  copy: TodayCopy,
): TodaySurface {
  if (input.data) {
    const incomplete = !sourcesComplete(input.data.coverage);
    if (input.data.items.length > 0) {
      return {
        kind: "list",
        items: input.data.items,
        note: incomplete || input.errorStatus ? copy.today_incomplete : null,
        stale: Boolean(input.errorStatus),
        generatedAt: input.data.generated_at,
        pulse: input.data.pulse,
        foldedCount: input.data.folded_count,
      };
    }
    if (!input.connected) {
      const canConnect = input.role === "owner" || input.role === "admin";
      return {
        kind: "connect",
        title: copy.today_connect_title,
        action: canConnect ? copy.connect_crm : null,
        detail: canConnect ? null : copy.today_connect_admin_detail,
      };
    }
    if (incomplete || input.errorStatus) {
      return {
        kind: "incomplete",
        title: copy.today_incomplete,
        generatedAt: input.data.generated_at,
      };
    }
    return { kind: "clear", title: copy.today_clear };
  }
  if (input.isLoading) return { kind: "loading" };
  if (input.errorStatus) return { kind: "error", title: copy.today_prepare_failed };
  if (!input.connected) {
    const canConnect = input.role === "owner" || input.role === "admin";
    return {
      kind: "connect",
      title: copy.today_connect_title,
      action: canConnect ? copy.connect_crm : null,
      detail: canConnect ? null : copy.today_connect_admin_detail,
    };
  }
  return { kind: "no-activity", title: copy.today_no_activity, actions: ["today_record", "open_contacts"] };
}

const SUPPORTING_KEYS: Record<string, string> = {
  commitment_due: "today_signal_commitment",
  going_cold: "today_signal_cold",
  objection_open: "today_signal_objection",
  manual_task: "today_origin_manual",
};

export function splitTodayItems(items: TodayItem[]): { calls: TodayItem[]; tasks: TodayItem[] } {
  const calls: TodayItem[] = [];
  const tasks: TodayItem[] = [];
  for (const item of items) {
    if (item.type === "manual_task") tasks.push(item);
    else calls.push(item);
  }
  return { calls, tasks };
}

export function signalLabelKey(type: string): string {
  return SUPPORTING_KEYS[type] || "today_origin_detected";
}

export function originKey(origins: string[]): "today_origin_manual" | "today_origin_detected" | "today_origin_both" {
  const manual = origins.includes("manual");
  const detected = origins.some((origin) => origin !== "manual");
  if (manual && detected) return "today_origin_both";
  if (manual) return "today_origin_manual";
  return "today_origin_detected";
}

export function supportingKeys(types: string[]): string[] {
  return types.flatMap((type) => (SUPPORTING_KEYS[type] ? [SUPPORTING_KEYS[type]] : []));
}

export function contactRecordUrl(
  provider: string | null,
  portalId: string | null,
  contactId: string | null,
): string | null {
  if (!contactId) return null;
  const name = (provider || "").trim().toLowerCase();
  if (name === "hubspot" && portalId) {
    return `https://app.hubspot.com/contacts/${portalId}/record/0-1/${contactId}`;
  }
  return null;
}

export function crmContactsUrl(provider: string | null, portalId: string | null): string | null {
  const name = (provider || "").trim().toLowerCase();
  if (name === "hubspot" && portalId) return `https://app.hubspot.com/contacts/${portalId}/objects/0-1`;
  if (name === "pipedrive") return "https://app.pipedrive.com/persons";
  return null;
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
