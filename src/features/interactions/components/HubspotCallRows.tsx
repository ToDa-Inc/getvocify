import { useState } from "react";
import { Phone, Timer } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import type { CrmCallRecording } from "@/features/recordings/types";
import { callDurationSeconds, formatCallDuration } from "@/lib/call-duration";
import { errorDetail } from "@/shared/lib/api-client";
import { useLanguage } from "@/lib/i18n";
import { timeLabel } from "@/lib/interactions";
import { CHANNEL_TILE } from "./InteractionRow";

const VISIBLE = 5;

/**
 * Calls made in HubSpot that Vocify has not read yet, each with the action that does it. Once
 * transcribing starts the call is a memo and moves to the list below.
 */
export function HubspotCallRows({
  calls,
  busyId,
  onTranscribe,
}: {
  calls: CrmCallRecording[];
  busyId: string | null;
  onTranscribe: (callId: string) => Promise<unknown>;
}) {
  const { t } = useLanguage();
  const copy = t.product.interactions.hubspotCalls;
  const locale = t.product.hourLocale;

  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? calls : calls.slice(0, VISIBLE);

  const start = (callId: string) =>
    onTranscribe(callId).catch((error) => toast.error(errorDetail(error, copy.failed)));

  return (
    <section aria-label={copy.title} className="space-y-1">
      <h2 className="px-3 text-[13px] font-medium text-muted-foreground">{copy.title}</h2>
      <ul className="space-y-0.5">
        {shown.map((call) => {
          const when = call.timestamp ?? (call.timestamp_ms ? new Date(call.timestamp_ms).toISOString() : null);
          const duration = formatCallDuration(callDurationSeconds(call));
          const busy = busyId === call.call_id;
          const subtitle = [call.author_name?.trim(), call.to_number].filter(Boolean).join(" · ");
          return (
            <li
              key={call.call_id}
              className="flex items-center gap-3.5 rounded-xl px-3 py-2.5 transition-colors duration-150 hover:bg-secondary/60 motion-reduce:transition-none"
            >
              <span
                aria-hidden
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] border ${CHANNEL_TILE.call}`}
              >
                <Phone className="h-[18px] w-[18px]" strokeWidth={1.5} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[15px] leading-snug text-foreground" title={call.title}>
                  {call.title}
                </p>
                {subtitle ? <p className="mt-0.5 truncate text-[13px] text-muted-foreground">{subtitle}</p> : null}
              </div>
              <div className="flex shrink-0 items-center gap-3.5 text-xs text-muted-foreground">
                <div className="w-[4.25rem] text-right tabular-nums leading-tight">
                  {when ? (
                    <time dateTime={when} className="block text-[13px] text-foreground/85">
                      {timeLabel(when, locale)}
                    </time>
                  ) : null}
                  {duration ? (
                    <span className="mt-0.5 inline-flex items-center gap-1 text-[11.5px]">
                      <Timer aria-hidden className="h-3 w-3" strokeWidth={1.5} />
                      {duration}
                    </span>
                  ) : null}
                </div>
                <Button variant="outline" size="sm" disabled={busy} onClick={() => void start(call.call_id)}>
                  {busy ? <VocifySpinner size={12} /> : null}
                  {busy ? copy.starting : copy.transcribe}
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
      {calls.length > VISIBLE ? (
        <Button variant="ghost" size="sm" className="ml-1" onClick={() => setExpanded((open) => !open)}>
          {expanded ? copy.showLess : copy.showMore.replace("{n}", String(calls.length - VISIBLE))}
        </Button>
      ) : null}
    </section>
  );
}
