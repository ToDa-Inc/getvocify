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

  const act = useCallback(async (item: TodayItem, action: "dismiss" | "confirm") => {
    if (!item.id || item.version == null) return;
    const requestId = crypto.randomUUID();
    const result = await todayApi.resolve(item.id, {
      action,
      request_id: requestId,
      expected_version: item.version,
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
  }, []);

  const dismiss = useCallback((item: TodayItem) => act(item, "dismiss"), [act]);
  const confirm = useCallback((item: TodayItem) => act(item, "confirm"), [act]);

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
