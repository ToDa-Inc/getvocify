import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useAuth } from "@/features/auth";
import { useIntegrations } from "@/features/integrations/hooks/useIntegrations";
import { cardsAfterDismiss, todaySurface, type TodayItem, type TodaySurface } from "@/lib/today";
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

export function useTodayCardActions() {
  const { user } = useAuth();
  const integrations = useIntegrations();
  const query = useToday();
  const acted = useSyncExternalStore(subscribeActed, getActedSnapshot, getActedSnapshot);

  const connected = (integrations.data ?? []).some((connection) => connection.status === "connected");
  const waiting = query.isLoading || integrations.isLoading;
  const surface: TodaySurface = todaySurface({
    data: query.data,
    errorStatus: query.isError ? statusOf(query.error) ?? 500 : null,
    isLoading: waiting && !query.data,
    connected: integrations.isLoading ? true : connected,
    role: user?.company?.role ?? "member",
  });

  const listed =
    surface.kind === "list" ? cardsAfterDismiss(surface.items, acted, Date.now()) : [];

  const dismiss = useCallback(async (item: TodayItem) => {
    if (!item.id || item.version == null) return;
    const result = await todayApi.resolve(item.id, {
      action: "dismiss",
      request_id: crypto.randomUUID(),
      expected_version: item.version,
    });
    setActedStore((current) => [
      ...current.filter((card) => card.id !== item.id),
      { ...item, status: result.status, version: result.version, undo_deadline: result.undo_deadline },
    ]);
  }, []);

  const undo = useCallback(async (item: TodayItem) => {
    if (!item.id || item.version == null) return;
    await todayApi.undo(item.id, {
      request_id: crypto.randomUUID(),
      expected_version: item.version,
    });
    setActedStore((current) => current.filter((card) => card.id !== item.id));
    await query.refetch();
  }, [query]);

  return { surface, listed, dismiss, undo, query };
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
