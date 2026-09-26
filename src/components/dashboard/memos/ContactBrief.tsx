import { useQuery } from "@tanstack/react-query";
import { briefRequest, visibleBrief, type BriefPayload, type BriefRow, type PanelBrief } from "@shared/ui/brief.js";
import { api } from "@/shared/lib/api-client";
import { THEME_TOKENS } from "@/lib/theme/tokens";

export function BriefLines({ brief, loadingText }: { brief: PanelBrief; loadingText: string }) {
  if (brief.state === "loading") {
    return <p className="text-[15px] leading-relaxed text-foreground">{loadingText}</p>;
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
      {brief.rows.map((row: BriefRow) => (
        <p
          key={row.text}
          className={`text-[15px] leading-relaxed text-foreground ${row.playbook ? "border-l-2 border-beige/60 pl-[11px]" : ""}`}
        >
          {row.text}
        </p>
      ))}
      {brief.label ? (
        <span className="v-chip mt-1 inline-flex w-fit rounded-full border border-border bg-cream px-2.5 py-0.5 text-[12px] text-muted-foreground">
          {brief.label}
        </span>
      ) : null}
    </div>
  );
}

export function ContactBrief({ contactId }: { contactId: string }) {
  const query = useQuery({
    queryKey: ["brief", contactId],
    queryFn: () => api.get<BriefPayload>(briefRequest(contactId)),
  });
  if (!query.data) return null;
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
