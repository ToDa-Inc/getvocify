import { ChevronDown, Phone, Timer } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import type { UnansweredOutcome } from "@/features/recordings/types";
import { formatCallDuration } from "@/lib/call-duration";
import { ApiError, errorDetail } from "@/shared/lib/api-client";
import { useLanguage } from "@/lib/i18n";
import { timeLabel, type CrmCallEntry } from "@/lib/interactions";
import { CHANNEL_TILE } from "./InteractionRow";

/**
 * A call the CRM logged that Vocify has not read: it sits in the list among the conversations, in the
 * same shape, with Transcribe where a conversation has its type, and beside it the way to keep it as
 * no answer or voicemail without transcribing it. Once either is done it is a conversation.
 */
export function CrmCallRow({
  call,
  busy,
  onTranscribe,
  onMarkUnanswered,
}: {
  call: CrmCallEntry;
  busy: boolean;
  onTranscribe: (callId: string) => Promise<unknown>;
  onMarkUnanswered: (callId: string, outcome: UnansweredOutcome) => Promise<unknown>;
}) {
  const { t } = useLanguage();
  const copy = t.product.interactions.crmCall;
  const locale = t.product.hourLocale;
  const duration = formatCallDuration(call.seconds);
  // The server's own words when it sent some; a request that never got an answer says so, not "Failed to fetch".
  const explain = (error: unknown, fallback: string) => {
    if (error instanceof ApiError) {
      const code = (error.data as { detail?: { code?: string } } | null)?.detail?.code;
      return code === "filed_under_teammate" ? copy.filedElsewhere : errorDetail(error, fallback);
    }
    return error instanceof TypeError ? copy.network : fallback;
  };
  const start = () => onTranscribe(call.id).catch((error) => toast.error(explain(error, copy.failed)));
  const mark = (outcome: UnansweredOutcome) =>
    onMarkUnanswered(call.id, outcome).catch((error) => toast.error(explain(error, copy.markFailed)));

  return (
    <li className="group relative flex items-center gap-3.5 rounded-xl px-3 py-2.5 transition-colors duration-150 hover:bg-secondary/60 motion-reduce:transition-none">
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
        <p className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[13px] text-muted-foreground">
          <span className="shrink-0">{copy.notTranscribed}</span>
          {call.subtitle ? (
            <>
              <span aria-hidden>·</span>
              <span className="truncate">{call.subtitle}</span>
            </>
          ) : null}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-3.5 text-xs text-muted-foreground">
        <div className="flex items-center">
          <Button variant="outline" size="sm" className="rounded-r-none" disabled={busy} onClick={() => void start()}>
            {busy ? <VocifySpinner size={12} /> : null}
            {busy ? copy.starting : copy.transcribe}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="-ml-px rounded-l-none px-1.5"
                disabled={busy}
                aria-label={copy.more}
                title={copy.more}
              >
                <ChevronDown aria-hidden className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => void mark("no_response")}>{copy.markNoAnswer}</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void mark("voicemail")}>{copy.markVoicemail}</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="w-[4.25rem] text-right tabular-nums leading-tight">
          <time dateTime={call.createdAt} className="block text-[13px] text-foreground/85">
            {timeLabel(call.createdAt, locale)}
          </time>
          {duration ? (
            <span className="mt-0.5 inline-flex items-center gap-1 text-[11.5px]">
              <Timer aria-hidden className="h-3 w-3" strokeWidth={1.5} />
              {duration}
            </span>
          ) : null}
        </div>
      </div>
    </li>
  );
}
