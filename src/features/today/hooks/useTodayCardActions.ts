import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useAuth } from "@/features/auth";
import { useIntegrations } from "@/features/integrations/hooks/useIntegrations";
import { useLanguage } from "@/lib/i18n";
import { cardsAfterDismiss, crmContactsUrl, todaySurface, type TodayItem, type TodaySurface } from "@/lib/today";
import { todayApi } from "../api";
import { useToday } from "./useToday";

function statusOf(error: unknown): number | null {
  if (typeof error === "object" && error && "status" in error) {
    const status = (error as { status?: unknown }).status;
    return typeof status === "number" ? status : null;
  }
  return error ? 500 : null;
}

let actedStore: TodayItem[] = [];
const actedListeners = new Set<() => void>();

function setActedStore(next: TodayItem[] | ((current: TodayItem[]) => TodayItem[])) {
  actedStore = typeof next === "function" ? next(actedStore) : next;
  actedListeners.forEach((listener) => listener());
}

function subscribeActed(listener: () => void) {
  actedListeners.add(listener);
  return () => actedListeners.delete(listener);
}

function getActedSnapshot() {
  return actedStore;
}

/** After a 409 the server row wins: drop the local result for that card. */
export function forgetActed(id: string) {
  setActedStore((current) => current.filter((card) => card.id !== id));
}

export function useTodayCardActions({ fresh = false }: { fresh?: boolean } = {}) {
  const { user } = useAuth();
  const { t } = useLanguage();
  const integrations = useIntegrations();
  const query = useToday({ fresh });
  const acted = useSyncExternalStore(subscribeActed, getActedSnapshot, getActedSnapshot);

  const connectedRow = (integrations.data ?? []).find((connection) => connection.status === "connected");
  const connected = Boolean(connectedRow);
  const contactsUrl = crmContactsUrl(
    connectedRow?.provider ?? null,
    connectedRow?.metadata?.portalId ?? null,
  );
  const waiting = query.isLoading || integrations.isLoading;
  const surface: TodaySurface = todaySurface({
    data: query.data,
    errorStatus: query.isError ? statusOf(query.error) ?? 500 : null,
    isLoading: waiting && !query.data,
    connected: integrations.isLoading ? true : connected,
    role: user?.company?.role ?? "member",
  }, t.product);

  const listed =
    surface.kind === "list" ? cardsAfterDismiss(surface.items, acted, Date.now()) : [];

  const act = useCallback(async (input: TodayItem, action: "dismiss" | "confirm" | "snooze" | "disqualify", until?: string) => {
    let item = input;
    // A never-contacted lead is computed on the fly and has no id yet: persist it first so
    // snooze/dismiss/disqualify (and their undo) work exactly like on any other card.
    const persisted = !item.id && item.type === "never_contacted" && Boolean(item.contact_id);
    if (persisted) {
      const row = await todayApi.persistNeverContacted({
        contact_id: String(item.contact_id),
        ...(item.connection_id ? { connection_id: item.connection_id } : {}),
      });
      item = { ...item, id: row.id, version: row.version, status: row.status };
    }
    if (!item.id || item.version == null) return;
    const requestId = crypto.randomUUID();
    const result = await todayApi.resolve(item.id, {
      action,
      request_id: requestId,
      expected_version: item.version,
      ...(until ? { until } : {}),
    });
    setActedStore((current) => [
      ...current.filter((card) => card.id !== item.id),
      {
        ...item,
        status: result.status,
        version: result.version,
        undo_deadline: result.undo_deadline,
        last_action_request_id: requestId,
      },
    ]);
    // The list still holds the id-less card: re-read so the server's row replaces it.
    if (persisted) await query.refetch();
  }, [query]);

  const dismiss = useCallback((item: TodayItem) => act(item, "dismiss"), [act]);
  const confirm = useCallback((item: TodayItem) => act(item, "confirm"), [act]);
  const snooze = useCallback((item: TodayItem, until: string) => act(item, "snooze", until), [act]);
  const disqualify = useCallback((item: TodayItem) => act(item, "disqualify"), [act]);

  const undo = useCallback(async (item: TodayItem) => {
    if (!item.id || item.version == null) return;
    const requestId = item.last_action_request_id;
    if (!requestId) return;
    await todayApi.undo(item.id, {
      request_id: requestId,
      expected_version: item.version,
    });
    setActedStore((current) => current.filter((card) => card.id !== item.id));
    await query.refetch();
  }, [query]);

  return {
    surface,
    listed,
    acted,
    dismiss,
    confirm,
    snooze,
    disqualify,
    undo,
    query,
    contactsUrl,
    connected: integrations.isLoading ? null : connected,
    provider: connectedRow?.provider ?? null,
    portalId: connectedRow?.metadata?.portalId ?? null,
  };
}

/** Re-render list rows while undo windows tick down. */
export function useTodayUndoClock(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(() => {
      actedListeners.forEach((listener) => listener());
    }, 1000);
    return () => window.clearInterval(id);
  }, [enabled]);
}
