import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, BookOpen, Check, ChevronLeft, ChevronRight, Copy, Lightbulb, RotateCw } from "lucide-react";
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

/** The state as a small tag: green when it went well, amber halfway, red not. */
const TAG = { bad: "bg-destructive/10 text-destructive", half: "bg-warning/10 text-warning", good: "bg-success/10 text-success", unknown: "bg-secondary text-muted-foreground" } as const;
const DOT = { bad: "bg-destructive/70", half: "bg-warning/80", good: "bg-success/70", unknown: "bg-muted-foreground/40" } as const;

type BubbleKind = "prospect" | "you" | "none" | "better";
const BUBBLE: Record<BubbleKind, string> = {
  prospect: "rounded-bl-md bg-secondary/70",
  you: "rounded-br-md bg-foreground/[0.06]",
  none: "rounded-br-md border border-dashed border-border text-muted-foreground",
  better: "rounded-br-md border border-success/25 bg-success/10",
};

/** One turn of the exchange: the prospect on the left, the rep on the right, with a small caption saying
 * whose it is. `actions` sit beside the bubble, away from the text. */
function Bubble({ kind, caption, children, actions }: { kind: BubbleKind; caption: string; children: ReactNode; actions?: ReactNode }) {
  const right = kind !== "prospect";
  return (
    <div className={cn("flex flex-col gap-0.5", right ? "items-end" : "items-start")}>
      <span className="px-1 text-[11px] text-muted-foreground">{caption}</span>
      <div className={cn("flex max-w-[94%] items-center gap-1", right && "flex-row-reverse")}>
        <div className={cn("min-w-0 rounded-2xl px-3.5 py-2 text-[14.5px] leading-snug text-foreground", BUBBLE[kind])}>{children}</div>
        {actions ? <span className="flex shrink-0 items-center">{actions}</span> : null}
      </div>
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
  // The playbook's own answer is what is shown while nothing better could be written (or it could not
  // be asked): a failure never leaves the moment without the playbook's way to say it.
  const shown = fallback ?? how;
  // The rep's own reply already did what the playbook asks, in their words: say so instead of rewriting it.
  if (reply.data?.reason === "already_fine") {
    return (
      <Bubble
        kind="better"
        caption={p.coachFineCaption}
        actions={
          <Link to={playbookHref} aria-label={p.coachSeePlaybook} title={p.coachSeePlaybook} className={cn(THEME_TOKENS.interaction.iconButton)}>
            <BookOpen className="h-4 w-4" strokeWidth={1.5} />
          </Link>
        }
      >
        <span className="flex items-start gap-2">
          <Check aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" strokeWidth={2} />
          <span className="min-w-0">{p.coachFine}</span>
        </span>
      </Bubble>
    );
  }
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
  } else if (reply.isError && !shown) {
    body = <span className="text-muted-foreground">{p.coachCouldNotWrite}</span>;
  } else {
    body = <span className={shown ? "" : "text-muted-foreground"}>{shown ?? p.coachNoPlaybookAnswer}</span>;
  }
  return (
    <Bubble
      kind="better"
      caption={say || reply.isPending ? p.coachBetter : p.coachBetterFallback}
      actions={
        <>
          {say ? (
            <IconAction label={copied ? p.coachCopied : p.coachCopy} onClick={copy}>
              {copied ? <Check className="h-4 w-4 text-success" strokeWidth={1.75} /> : <Copy className="h-4 w-4" strokeWidth={1.5} />}
            </IconAction>
          ) : null}
          {reply.isError ? (
            <IconAction label={p.coachRetry} pending={reply.isFetching} onClick={() => void reply.refetch()}>
              <RotateCw className="h-4 w-4" strokeWidth={1.5} />
            </IconAction>
          ) : null}
          <Link to={playbookHref} aria-label={p.coachSeePlaybook} title={p.coachSeePlaybook} className={cn(THEME_TOKENS.interaction.iconButton)}>
            <BookOpen className="h-4 w-4" strokeWidth={1.5} />
          </Link>
        </>
      }
    >
      <span className="flex items-start gap-2">
        <Lightbulb aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" strokeWidth={1.75} />
        <span className="min-w-0">{body}</span>
      </span>
    </Bubble>
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
        <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium", TAG[moment.tone])}>
          <span aria-hidden className={cn("h-1.5 w-1.5 rounded-full", DOT[moment.tone])} />
          {stateWord}
        </span>
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
            <Bubble kind="prospect" caption={p.coachProspectSaid}>{moment.quote ?? "—"}</Bubble>
            {moment.response ? <Bubble kind="you" caption={p.coachYouReplied}>{moment.response}</Bubble> : <Bubble kind="none" caption={p.coachYouReplied}>{p.coachNoReply}</Bubble>}
          </>
        ) : moment.quote ? (
          <Bubble kind="you" caption={p.coachYouSaid}>{moment.quote}</Bubble>
        ) : (
          <p className="text-[13.5px] leading-snug text-muted-foreground">{moment.reason ?? stateWord}</p>
        )}
        {!objection && moment.tone === "good" && moment.quote && moment.reason ? (
          <p className="text-[13.5px] leading-snug text-muted-foreground">{moment.reason}</p>
        ) : null}
        <Better request={request} how={objection ? how : null} fallback={objection ? null : moment.advice ?? how} playbookHref={href} show={moment.tone !== "good"} />
      </div>
    </div>
  );
}
