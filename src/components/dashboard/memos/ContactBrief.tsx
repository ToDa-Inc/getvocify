import { useQuery } from "@tanstack/react-query";
import {
  BRIEF_LOADING,
  briefRequest,
  panelBrief,
  visibleBrief,
  type BriefPayload,
  type BriefRow,
  type PanelBrief,
} from "@shared/ui/brief.js";
import { api } from "@/shared/lib/api-client";
import { THEME_TOKENS } from "@/lib/theme/tokens";

export function BriefLines({ brief, loadingText, compact }: { brief: PanelBrief; loadingText: string; compact?: boolean }) {
  const bodyClass = compact ? "text-[12px] leading-snug text-muted-foreground" : "text-[15px] leading-relaxed text-foreground";
  const chipClass = compact
    ? "v-chip mt-1 inline-flex w-fit rounded-full border border-border bg-cream px-2 py-0.5 text-[11px] text-muted-foreground"
    : "v-chip mt-1 inline-flex w-fit rounded-full border border-border bg-cream px-2.5 py-0.5 text-[12px] text-muted-foreground";

  if (brief.state === "loading") {
    return <p className={bodyClass}>{loadingText}</p>;
  }
  if (brief.state === "failed") {
    return <p className={`${THEME_TOKENS.typography.body} text-foreground`}>{brief.notice}</p>;
  }
  if (brief.state === "none" && !brief.rows.length && !brief.notice) return null;

  return (
    <div className="grid gap-2">
      {brief.notice ? (
        <p className={`${THEME_TOKENS.typography.body} text-foreground`}>{brief.notice}</p>
      ) : null}
      {brief.rows.map((row: BriefRow, index: number) => (
        <p
          key={`${index}-${row.text}`}
          className={`${bodyClass} ${row.playbook ? "border-l-2 border-beige/60 pl-[11px]" : ""}`}
        >
          {row.text}
        </p>
      ))}
      {brief.label ? <span className={chipClass}>{brief.label}</span> : null}
    </div>
  );
}

/** Only BRIEF_V2_ENABLED answers carry `label` (null when there is none). */
function isV2(payload: BriefPayload): boolean {
  return Object.prototype.hasOwnProperty.call(payload, "label");
}

export function ContactBrief({ contactId, compact = false }: { contactId: string; compact?: boolean }) {
  const query = useQuery({
    queryKey: ["brief", contactId],
    queryFn: () => api.get<BriefPayload>(briefRequest(contactId)),
    staleTime: 30_000,
  });

  if (!query.data) {
    if (!compact) return null;
    const brief = panelBrief({
      contactId,
      cache: null,
      flightContactId: query.isPending ? contactId : null,
      failedContactId: query.isError ? contactId : null,
    });
    if (brief.state !== "loading") return null;
    return (
      <section aria-label="Antes de llamar" className="space-y-1">
        <BriefLines brief={brief} loadingText={BRIEF_LOADING} compact />
      </section>
    );
  }

  if (!compact && !isV2(query.data)) {
    const lines = visibleBrief(query.data);
    if (lines.length === 0) return null;
    return (
      <section aria-label="Antes de llamar" className="space-y-1">
        {lines.map((line, index) => (
          <p key={`${index}-${line}`}>{line}</p>
        ))}
      </section>
    );
  }

  const brief = panelBrief({ contactId, cache: { contactId, brief: query.data }, flightContactId: null });
  if (!brief.rows.length && !brief.notice && !brief.label) return null;
  return (
    <section aria-label="Antes de llamar" className="space-y-1">
      <BriefLines brief={brief} loadingText={BRIEF_LOADING} compact={compact} />
    </section>
  );
}
