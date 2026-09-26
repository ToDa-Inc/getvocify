import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BRIEF_LOADING,
  briefRequest,
  panelBrief,
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
          className={`${bodyClass} text-foreground ${row.playbook ? "border-l-2 border-beige/60 pl-[11px]" : ""}`}
        >
          {row.text}
        </p>
      ))}
      {brief.label ? <span className={chipClass}>{brief.label}</span> : null}
    </div>
  );
}

export function ContactBrief({
  contactId,
  connectionId,
  compact = false,
}: {
  contactId: string;
  connectionId?: string | null;
  compact?: boolean;
}) {
  const query = useQuery({
    queryKey: ["brief", contactId, connectionId ?? "hubspot"],
    queryFn: () => api.get<BriefPayload>(briefRequest(contactId, connectionId ?? undefined)),
    staleTime: 30_000,
  });

  const brief = useMemo(() => {
    const cache = contactId && query.data ? { contactId, brief: query.data } : null;
    const flightContactId = query.isPending && contactId ? contactId : null;
    const failedContactId = query.isError && contactId ? contactId : null;
    return panelBrief({ contactId, cache, flightContactId, failedContactId });
  }, [contactId, query.data, query.isError, query.isPending]);

  if (brief.state === "none" && !brief.rows.length && !brief.notice) return null;

  return (
    <section aria-label="Antes de llamar" className={compact ? "space-y-1" : "space-y-1"}>
      <BriefLines brief={brief} loadingText={BRIEF_LOADING} compact={compact} />
    </section>
  );
}
