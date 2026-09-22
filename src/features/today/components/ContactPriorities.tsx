import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { prioritySurface } from "@/lib/contact-priorities";
import { useLanguage } from "@/lib/i18n";
import { productText } from "@/lib/product-catalog";
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
  const { t } = useLanguage();
  const copy = t.product;
  const query = useContactPriorities();
  const surface = prioritySurface({
    data: query.data,
    errorStatus: query.isError ? statusOf(query.error) ?? 500 : null,
    isLoading: query.isLoading,
  });

  function runAction(action: string) {
    if (action === "retry") {
      void query.refetch();
      return;
    }
    if (action === "connect_crm" || action === "map_owners") {
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
        <p role="alert">{productText(surface.title, copy)}</p>
      ) : null}
      {surface.kind === "empty" ? (
        <div>
          <p>{productText(surface.title, copy)}</p>
          {surface.action === "open_contacts" && surface.contactsUrl ? (
            <a href={surface.contactsUrl} target="_blank" rel="noreferrer">
              {productText(surface.action, copy)}
            </a>
          ) : surface.action === "retry" || surface.action === "connect_crm" || surface.action === "map_owners" ? (
            <Button type="button" variant="outline" onClick={() => runAction(surface.action as string)}>
              {productText(surface.action, copy)}
            </Button>
          ) : surface.action ? (
            <p>{productText(surface.action, copy)}</p>
          ) : null}
        </div>
      ) : null}
      {surface.kind === "list" ? (
        <ul className="space-y-3">
          {surface.note ? <p>{productText(surface.note, copy)}</p> : null}
          {surface.stale ? <p>Mostrando la última lectura.</p> : null}
          {surface.items.map((item) => (
            <li key={item.id} className="rounded-lg border p-4">
              <p>{productText(item.reason, copy)}</p>
              {item.next_action ? <p>{productText(item.next_action, copy)}</p> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
