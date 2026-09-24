import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { priorityCards, prioritySurface } from "@/lib/contact-priorities";
import { useLanguage } from "@/lib/i18n";
import { productText } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { useContactPriorities } from "../hooks/useContactPriorities";
import type { PrioritySurface } from "@/lib/contact-priorities";
import type { ProductTranslations } from "@/lib/product-catalog";

function PriorityList({
  surface,
  copy,
  card,
}: {
  surface: Extract<PrioritySurface, { kind: "list" }>;
  copy: ProductTranslations;
  card: string;
}) {
  const shown = priorityCards(surface.items);
  const note = surface.note || shown.note;
  return (
    <ul className="space-y-3">
      {note ? <p className={THEME_TOKENS.typography.body}>{productText(note, copy)}</p> : null}
      {surface.stale ? <p className={THEME_TOKENS.typography.capsLabel}>{copy.contactPrioritiesStale}</p> : null}
      {shown.items.map((item) => (
        <li key={item.id} className={card}>
          <p className="text-[15px] leading-relaxed text-foreground">{productText(item.reason, copy)}</p>
          {item.next_action ? <p className={THEME_TOKENS.typography.body}>{productText(item.next_action, copy)}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function statusOf(error: unknown): number | null {
  if (typeof error === "object" && error && "status" in error) {
    const status = (error as { status?: unknown }).status;
    return typeof status === "number" ? status : null;
  }
  return error ? 500 : null;
}

export function ContactPriorities({ hideEmpty = false, embedded = false }: { hideEmpty?: boolean; embedded?: boolean }) {
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

  const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-2`;

  return (
    <section aria-labelledby={embedded ? undefined : "contact-priorities-title"} className="space-y-3">
      {embedded ? null : (
        <h2 id="contact-priorities-title" className={THEME_TOKENS.typography.sectionTitle}>
          {copy.contactPrioritiesTitle}
        </h2>
      )}
      {surface.kind === "loading" ? <p className={THEME_TOKENS.typography.body}>{copy.contactPrioritiesLoading}</p> : null}
      {surface.kind === "error" ? (
        <p className={THEME_TOKENS.typography.body} role="alert">{productText(surface.title, copy)}</p>
      ) : null}
      {surface.kind === "empty" ? (
        <div className={card}>
          <p className="text-[15px] text-foreground">{productText(surface.title, copy)}</p>
          {surface.action === "open_contacts" && surface.contactsUrl ? (
            <a className="text-sm text-beige" href={surface.contactsUrl} target="_blank" rel="noreferrer">
              {productText(surface.action, copy)}
            </a>
          ) : surface.action === "retry" || surface.action === "connect_crm" || surface.action === "map_owners" ? (
            <Button type="button" variant="outline" size="sm" onClick={() => runAction(surface.action as string)}>
              {productText(surface.action, copy)}
            </Button>
          ) : surface.action ? (
            <p className={THEME_TOKENS.typography.body}>{productText(surface.action, copy)}</p>
          ) : null}
        </div>
      ) : null}
      {surface.kind === "list" ? (
        <PriorityList surface={surface} copy={copy} card={card} />
      ) : null}
    </section>
  );
}
