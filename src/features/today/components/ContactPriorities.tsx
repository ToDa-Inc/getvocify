import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { prioritySurface } from "@/lib/contact-priorities";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { useContactPriorities } from "../hooks/useContactPriorities";

function statusOf(error: unknown): number | null {
  if (typeof error === "object" && error && "status" in error) {
    const status = (error as { status?: unknown }).status;
    return typeof status === "number" ? status : null;
  }
  return error ? 500 : null;
}

export function ContactPriorities({ hideEmpty = false }: { hideEmpty?: boolean }) {
  const navigate = useNavigate();
  const query = useContactPriorities();
  const surface = prioritySurface({
    data: query.data,
    errorStatus: query.isError ? statusOf(query.error) ?? 500 : null,
    isLoading: query.isLoading,
  });

  function runAction(action: string) {
    if (action === "Reintentar") {
      void query.refetch();
      return;
    }
    if (action === "Conectar CRM" || action === "Mapear responsables") {
      navigate("/dashboard/settings/integrations");
    }
  }

  if (hideEmpty && surface.kind === "empty") return null;

  return (
    <section aria-labelledby="contact-priorities-title" className="space-y-3">
      <h2 id="contact-priorities-title" className={THEME_TOKENS.typography.pageTitle}>
        A quién contactar
      </h2>
      {surface.kind === "loading" ? <p>Leyendo el CRM…</p> : null}
      {surface.kind === "error" ? (
        <p role="alert">{surface.title}</p>
      ) : null}
      {surface.kind === "empty" ? (
        <div>
          <p>{surface.title}</p>
          {surface.action === "Reintentar" || surface.action === "Conectar CRM" || surface.action === "Mapear responsables" ? (
            <Button type="button" variant="outline" onClick={() => runAction(surface.action as string)}>
              {surface.action}
            </Button>
          ) : surface.action ? (
            <p>{surface.action}</p>
          ) : null}
        </div>
      ) : null}
      {surface.kind === "list" ? (
        <ul className="space-y-3">
          {surface.note ? <p>{surface.note}</p> : null}
          {surface.stale ? <p>Mostrando la última lectura.</p> : null}
          {surface.items.map((item) => (
            <li key={item.id} className="rounded-lg border p-4">
              <p>{item.reason}</p>
              {item.next_action ? <p>{item.next_action}</p> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
