import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth";
import { useIntegrations } from "@/features/integrations/hooks/useIntegrations";
import { todaySurface } from "@/lib/today";
import { THEME_TOKENS } from "@/lib/theme/tokens";
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
  const connected = (integrations.data ?? []).some((connection) => connection.status === "connected");
  const waiting = query.isLoading || integrations.isLoading;
  const surface = todaySurface({
    data: query.data,
    errorStatus: query.isError ? statusOf(query.error) ?? 500 : null,
    isLoading: waiting && !query.data,
    connected: integrations.isLoading ? true : connected,
    role: user?.company?.role ?? "member",
  });

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
            {surface.items.map((item) => (
              <li key={item.dedupe_key ?? item.remote_id ?? item.reason} className="rounded-lg border p-4">
                <p>{item.reason}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
