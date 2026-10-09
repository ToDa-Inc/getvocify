import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth";
import type { Memo } from "@/features/memos/types";
import { api } from "@/shared/lib/api-client";
import {
  conversationLine,
  handoffHistoryRequest,
  handoffHistoryTitle,
  showsHandoffHistory,
} from "@/lib/contact-panel";
import { useLanguage } from "@/lib/i18n";
import { productText } from "@/lib/product-catalog";
import { plainSummary } from "@/lib/summary-line";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/**
 * T4/D8: "Lo que habló {SDR}" - the SDR's memos for a contact handed off to this rep.
 * Only for the AE/General side of a handoff (never the SDR reading themselves back) and
 * only with HANDOFF_ENABLED. scope=handoffs returns nothing without an active-or-closed
 * handoff for this contact, so an empty result renders nothing - it is not an error.
 * Shared by the contact panel and the AE's deal card.
 */
export function HandoffHistory({
  contactId,
  onOpenMemo,
  divider = false,
}: {
  contactId: string | null | undefined;
  onOpenMemo: (memoId: string) => void;
  divider?: boolean;
}) {
  const { t } = useLanguage();
  const copy = t.product;
  const { user } = useAuth();
  const handoffEnabled = Boolean(user?.company?.features?.includes("HANDOFF_ENABLED"));
  const canRead = handoffEnabled && user?.company?.salesRole !== "sdr";
  const query = useQuery({
    queryKey: ["home-panel-handoff-history", contactId],
    queryFn: () => api.get<Memo[]>(handoffHistoryRequest(contactId as string)),
    enabled: Boolean(contactId && canRead),
    staleTime: 30_000,
  });
  const sdrName = query.data?.[0]?.authorName ?? null;
  if (!contactId || !query.data || !showsHandoffHistory(canRead, sdrName)) return null;

  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const title = handoffHistoryTitle(copy.panel_handoff_history_title, sdrName as string);
  return (
    <>
      {divider ? <hr className="my-5 border-0 border-t border-[hsl(var(--hairline))]" /> : null}
      <section aria-label={title}>
        <p className={`mb-3 ${THEME_TOKENS.typography.capsLabel}`}>{title}</p>
        <ul className="grid gap-3.5">
          {query.data.map((memo) => {
            const line = conversationLine(memo, { locale: copy.hourLocale, timeZone });
            const kindLabel = productText(line.kindKey, copy);
            const minutes = line.minutes != null ? copy.panel_minutes.replace("{count}", String(line.minutes)) : null;
            const meta = [line.date, kindLabel, minutes].filter(Boolean).join(" · ");
            const summary = plainSummary(memo.extraction?.summary);
            return (
              <li key={memo.id}>
                <button type="button" className="w-full text-left" onClick={() => onOpenMemo(String(memo.id))}>
                  <p className={THEME_TOKENS.typography.capsLabel}>{meta}</p>
                  {summary ? (
                    <p className="mt-0.5 line-clamp-2 text-[14px] leading-snug text-foreground/90">{summary}</p>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      </section>
    </>
  );
}
