import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, BookOpen, Check, ChevronLeft, ChevronRight, Copy, Lightbulb } from "lucide-react";
import { IconAction } from "@/components/ui/icon-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { useBetterReply, type BetterReplyRequest } from "./useBetterReply";

export type Moment = {
  memo_id: string;
  observed_at: string;
  /** How it went: bad = not done / left open, half = halfway, good = done / resolved, unknown = unclear. */
  tone: "bad" | "half" | "good" | "unknown";
  /** The prospect's words (an objection) or the rep's (a step). */
  quote: string | null;
  /** The rep's reply to an objection. */
  response: string | null;
  /** What went wrong, for a step. */
  reason: string | null;
  /** The call reading's own advice for a step: the fallback when no line could be written. */
  advice: string | null;
};

const DOT = { bad: "bg-destructive/70", half: "bg-warning/80", good: "bg-success/70", unknown: "bg-muted-foreground/40" } as const;

function Line({ label, children, accent = false }: { label: string; children: ReactNode; accent?: boolean }) {
  return (
    <div className={cn("grid grid-cols-[5.25rem_minmax(0,1fr)] items-baseline gap-3", accent && "border-l-2 border-success/60 pl-3 -ml-3.5")}>
      <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{label}</span>
      <div className="min-w-0 text-[14.5px] leading-snug text-foreground">{children}</div>
    </div>
  );
}

/** The line to say, written for this moment. A copy icon, a link to where the playbook says it, and
 * an honest line when the playbook gives nothing to write one from. */
function Better({ request, how, fallback, playbookHref, show }: { request: BetterReplyRequest; how: string | null; fallback: string | null; playbookHref: string; show: boolean }) {
  const { t } = useLanguage();
  const p = t.product;
  const reply = useBetterReply(request, show);
  const [copied, setCopied] = useState(false);
  if (!show) return null;
  const say = reply.data?.say ?? null;
  const copy = () => {
    if (!say) return;
    void navigator.clipboard?.writeText(say).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  };
  let body: ReactNode;
  if (reply.isPending) {
    body = (
      <span className="inline-flex items-center gap-2 text-muted-foreground">
        <VocifySpinner size={12} />
        {p.coachWriting}
      </span>
    );
  } else if (say) {
    body = <span className="font-medium">{say}</span>;
  } else if (reply.isError) {
    body = (
      <span className="text-muted-foreground">
        {p.coachCouldNotWrite}{" "}
        <button type="button" className="underline underline-offset-2 hover:text-foreground" onClick={() => void reply.refetch()}>{p.coachRetry}</button>
      </span>
    );
  } else {
    const shown = fallback ?? how;
    body = <span className={shown ? "" : "text-muted-foreground"}>{shown ?? p.coachNoPlaybookAnswer}</span>;
  }
  return (
    <Line label={say || reply.isPending ? p.coachBetter : p.coachBetterFallback} accent>
      <div className="flex items-start gap-2">
        <Lightbulb aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" strokeWidth={1.75} />
        <div className="min-w-0 flex-1">{body}</div>
        <span className="-my-1.5 flex shrink-0 items-center">
          {say ? (
            <IconAction label={copied ? p.coachCopied : p.coachCopy} onClick={copy}>
              {copied ? <Check className="h-4 w-4 text-success" strokeWidth={1.75} /> : <Copy className="h-4 w-4" strokeWidth={1.5} />}
            </IconAction>
          ) : null}
          <Link to={playbookHref} aria-label={p.coachSeePlaybook} title={p.coachSeePlaybook} className={cn(THEME_TOKENS.interaction.iconButton)}>
            <BookOpen className="h-4 w-4" strokeWidth={1.5} />
          </Link>
        </span>
      </div>
    </Line>
  );
}

/** One moment at a time: when, what was said, and what to say instead. The arrows go through the rest;
 * nothing else is on screen, so the row opens to something that can be read in five seconds. */
export function OccurrencePager({ type, kind, itemKey, how, moments }: { type: string; kind: "step" | "objection"; itemKey: string; how: string | null; moments: Moment[] }) {
  const { t, language } = useLanguage();
  const p = t.product;
  const [index, setIndex] = useState(0);
  const moment = moments[index];
  if (!moment) return null;
  const objection = kind === "objection";
  const stateWord = { bad: objection ? p.coachObjectionOpen : p.coachStateMissing, half: p.coachStateImprovable, good: objection ? p.coachObjectionResolved : p.coachStateDone, unknown: p.coachObjectionUnknown }[moment.tone];
  const day = new Date(moment.observed_at).toLocaleDateString(language === "EN" ? "en-GB" : "es-ES", { day: "numeric", month: "short" });
  const request: BetterReplyRequest = { type, kind, key: itemKey, memo_id: moment.memo_id, quote: moment.quote, response: moment.response, reason: moment.reason };
  const href = `/dashboard/coach?tab=playbook&type=${encodeURIComponent(type)}`;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span aria-hidden className={cn("h-2 w-2 rounded-full", DOT[moment.tone])} />
        <span>{stateWord}</span>
        <Link to={`/dashboard/memos/${moment.memo_id}`} className="inline-flex items-center gap-0.5 hover:text-foreground">
          {day}
          <ArrowUpRight aria-hidden className="h-3 w-3" />
        </Link>
        {moments.length > 1 ? (
          <span className="ml-auto inline-flex items-center">
            <button type="button" aria-label={p.coachPrevious} disabled={index === 0} onClick={() => setIndex(index - 1)} className={cn(THEME_TOKENS.interaction.iconButton, "h-7 w-7")}>
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="min-w-9 text-center tabular-nums">{index + 1}/{moments.length}</span>
            <button type="button" aria-label={p.coachNext} disabled={index === moments.length - 1} onClick={() => setIndex(index + 1)} className={cn(THEME_TOKENS.interaction.iconButton, "h-7 w-7")}>
              <ChevronRight className="h-4 w-4" />
            </button>
          </span>
        ) : null}
      </div>
      <div className="space-y-2.5">
        {objection ? (
          <>
            <Line label={p.coachProspectSaid}>{moment.quote ? <span className="italic">«{moment.quote}»</span> : "—"}</Line>
            <Line label={p.coachYouReplied}>
              {moment.response ? <span className="italic">«{moment.response}»</span> : <span className="text-muted-foreground">{p.coachNoReply}</span>}
            </Line>
          </>
        ) : moment.quote ? (
          <Line label={p.coachYouSaid}><span className="italic">«{moment.quote}»</span></Line>
        ) : (
          <Line label={p.coachWhatHappened}><span className="text-muted-foreground">{moment.reason ?? stateWord}</span></Line>
        )}
        <Better request={request} how={objection ? how : null} fallback={objection ? null : moment.advice ?? how} playbookHref={href} show={moment.tone !== "good"} />
      </div>
    </div>
  );
}
