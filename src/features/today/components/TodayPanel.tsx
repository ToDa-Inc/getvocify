import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth";
import { useIntegrations } from "@/features/integrations/hooks/useIntegrations";
import { cardsAfterDismiss, todaySurface, type TodayItem } from "@/lib/today";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { todayApi } from "../api";
import { useToday } from "../hooks/useToday";

function statusOf(error: unknown): number | null {
  if (typeof error === "object" && error && "status" in error) {
    const status = (error as { status?: unknown }).status;
    return typeof status === "number" ? status : null;
  }
  return error ? 500 : null;
}

export function TodayPanel() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const integrations = useIntegrations();
  const query = useToday();
  const [acted, setActed] = useState<TodayItem[]>([]);
  const connected = (integrations.data ?? []).some((connection) => connection.status === "connected");
  const waiting = query.isLoading || integrations.isLoading;
  const surface = todaySurface({
    data: query.data,
    errorStatus: query.isError ? statusOf(query.error) ?? 500 : null,
    isLoading: waiting && !query.data,
    connected: integrations.isLoading ? true : connected,
    role: user?.company?.role ?? "member",
  });

  async function dismiss(item: TodayItem) {
    if (!item.id || item.version == null) return;
    const result = await todayApi.resolve(item.id, {
      action: "dismiss",
      request_id: crypto.randomUUID(),
      expected_version: item.version,
    });
    setActed((current) => [
      ...current.filter((card) => card.id !== item.id),
      { ...item, status: result.status, version: result.version, undo_deadline: result.undo_deadline },
    ]);
  }

  async function undo(item: TodayItem) {
    if (!item.id || item.version == null) return;
    await todayApi.undo(item.id, {
      request_id: crypto.randomUUID(),
      expected_version: item.version,
    });
    setActed((current) => current.filter((card) => card.id !== item.id));
    await query.refetch();
  }

  const listed = surface.kind === "list" ? cardsAfterDismiss(surface.items, acted, Date.now()) : [];

  return (
    <section aria-labelledby="today-title" aria-busy={surface.kind === "loading"} className="space-y-3">
      <h2 id="today-title" className={THEME_TOKENS.typography.pageTitle}>Hoy</h2>
      {surface.kind === "loading" ? (
        <div className="space-y-3" aria-hidden="true">
          <div className="h-16 rounded-lg border" />
          <div className="h-16 rounded-lg border" />
          <div className="h-16 rounded-lg border" />
        </div>
      ) : null}
      {surface.kind === "error" ? <p role="alert">{surface.title}</p> : null}
      {surface.kind === "connect" ? (
        <div>
          <p>{surface.title}</p>
          {surface.detail ? <p>{surface.detail}</p> : null}
          {surface.action ? (
            <Button type="button" variant="outline" onClick={() => navigate("/dashboard/settings/integrations")}>
              {surface.action}
            </Button>
          ) : null}
        </div>
      ) : null}
      {surface.kind === "no-activity" ? <p>{surface.title}</p> : null}
      {surface.kind === "incomplete" ? (
        <p>{surface.title}{surface.generatedAt ? ` · ${surface.generatedAt}` : ""}</p>
      ) : null}
      {surface.kind === "clear" ? <p>{surface.title}</p> : null}
      {surface.kind === "list" ? (
        <div className="space-y-3">
          {surface.note ? <p>{surface.note}{surface.generatedAt ? ` · ${surface.generatedAt}` : ""}</p> : null}
          <ul className="space-y-3">
            {listed.map((item) => {
              const undoOpen = item.undo_deadline != null && Date.parse(item.undo_deadline) >= Date.now();
              return (
                <li key={item.id ?? item.dedupe_key ?? item.remote_id ?? item.reason} className="rounded-lg border p-4">
                  <p>{item.reason}</p>
                  {item.id && item.status !== "dismissed" ? (
                    <Button type="button" variant="outline" onClick={() => void dismiss(item)}>Descartar</Button>
                  ) : null}
                  {undoOpen ? (
                    <Button type="button" variant="outline" onClick={() => void undo(item)}>Deshacer</Button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
