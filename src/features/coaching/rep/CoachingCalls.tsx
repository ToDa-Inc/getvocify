import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BookOpen,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  CircleX,
  Lightbulb,
  MessageCircle,
  Quote as QuoteIcon,
  type LucideIcon,
} from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Segmented } from "@/components/ui/segmented";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import {
  cleanSummaryLine,
  countTone,
  durationLabel,
  fill,
  improveBeforeLine,
  improveCountLine,
  type CoachCall,
  type CoachCalls,
  type CoachImprove,
  type CoachSlip,
} from "@/lib/rep-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { CoachEmpty, CoachError, CoachLoading } from "./CoachingState";
import { useCoachCalls } from "./useRepCoaching";

const ROW = "rounded-xl px-3 py-2.5 transition-colors duration-150 hover:bg-secondary/60 motion-reduce:transition-none";
const CHIP = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-medium leading-5";

/** One look per state, everywhere: red for not done, amber for done halfway, green for done. */
const SLIP_LOOK: Record<CoachSlip["state"], { icon: LucideIcon; chip: string; labelKey: "coachStateMissing" | "coachStateImprovable" }> = {
  missing: { icon: CircleX, chip: THEME_TOKENS.colors.danger, labelKey: "coachStateMissing" },
  improvable: { icon: CircleAlert, chip: THEME_TOKENS.colors.warning, labelKey: "coachStateImprovable" },
};
const TONE_TEXT = { success: "text-success", warning: "text-warning", destructive: "text-destructive", muted: "text-foreground" } as const;

/** Not done first, then halfway: the order of the chips and of a call's detail. */
function bySeverity(slips: CoachSlip[]): CoachSlip[] {
  return [...slips].sort((a, b) => Number(a.state !== "missing") - Number(b.state !== "missing"));
}

function localeOf(language: string) {
  return language === "EN" ? "en-GB" : "es-ES";
}

function dayLabel(iso: string | null, language: string): string {
  const at = iso ? new Date(iso) : null;
  if (!at || Number.isNaN(at.getTime())) return "";
  return at.toLocaleDateString(localeOf(language), { weekday: "short", day: "numeric", month: "short" });
}

function timeLabel(iso: string | null, language: string): string {
  const at = iso ? new Date(iso) : null;
  if (!at || Number.isNaN(at.getTime())) return "";
  return at.toLocaleTimeString(localeOf(language), { hour: "2-digit", minute: "2-digit" });
}

/** "No hecho" / "Mejorable" as a coloured pill with its icon. */
function StatePill({ state }: { state: CoachSlip["state"] }) {
  const { t } = useLanguage();
  const look = SLIP_LOOK[state];
  const Icon = look.icon;
  return (
    <span className={cn(CHIP, look.chip)}>
      <Icon aria-hidden className="h-3 w-3" strokeWidth={2} />
      {t.product[look.labelKey]}
    </span>
  );
}

/** A labelled line: what it is on the left (icon + label), the content on the right; stacked on a phone. */
function Field({ icon: Icon, label, children }: { icon: LucideIcon; label: ReactNode; children: ReactNode }) {
  return (
    <div className="grid gap-1.5 sm:grid-cols-[10.5rem_minmax(0,1fr)] sm:gap-4">
      <p className="flex items-start gap-1.5 pt-0.5 text-[12.5px] font-medium text-muted-foreground">
        <Icon aria-hidden className="mt-px h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
        <span>{label}</span>
      </p>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** The moment of the call, as said: a quiet bubble, so it never reads like the advice. */
function Moment({ text }: { text: string }) {
  return (
    <blockquote className={`${THEME_TOKENS.radius.control} bg-secondary/70 px-3.5 py-2.5 text-sm italic leading-relaxed text-foreground/80`}>
      «{text}»
    </blockquote>
  );
}

/** What to try next time: the one line a rep should take into the next call, so it stands out in green. */
function NextTime({ text }: { text: string }) {
  return (
    <p className={`${THEME_TOKENS.radius.control} border border-success/25 bg-success/10 px-3.5 py-2.5 text-sm leading-relaxed text-foreground`}>
      {text}
    </p>
  );
}

/** The what / moment / next-time trio of a slipped step, the same in "En qué mejorar" and in each call. */
function SlipFields({ reason, quote, advice, extra }: { reason: string | null; quote: string | null; advice: string | null; extra?: ReactNode }) {
  const { t } = useLanguage();
  const p = t.product;
  return (
    <>
      {reason || extra ? (
        <Field icon={MessageCircle} label={p.coachSlipWhat}>
          {reason ? <p className="text-sm leading-relaxed text-foreground">{reason}</p> : null}
          {extra}
        </Field>
      ) : null}
      {quote ? (
        <Field icon={QuoteIcon} label={p.coachSlipMoment}>
          <Moment text={quote} />
        </Field>
      ) : null}
      {advice ? (
        <Field icon={Lightbulb} label={<span className="text-success">{p.coachImproveHow}</span>}>
          <NextTime text={advice} />
        </Field>
      ) : null}
    </>
  );
}

/** One of the one or two steps slipped most: what the playbook asks, a call that shows it, how to do it. */
function ImproveItem({ item, weeks, index }: { item: CoachImprove; weeks: number; index: number }) {
  const { t, language } = useLanguage();
  const p = t.product;
  const before = improveBeforeLine(p, item, weeks);
  const example = item.example;
  return (
    <article className="border-t border-border/60 py-6 first:border-t-0 first:pt-2" data-testid="coach-improve-item">
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className={cn("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold tabular-nums", THEME_TOKENS.colors.warning)}
        >
          {index + 1}
        </span>
        <div className="min-w-0 space-y-1">
          <h3 className="text-[17px] font-semibold tracking-tight text-foreground">{item.label}</h3>
          <p className="flex flex-wrap items-center gap-1.5">
            {/* rounded-md, not a pill: on a phone this line wraps. */}
            <span className={cn(CHIP, "rounded-md", item.missing ? THEME_TOKENS.colors.danger : THEME_TOKENS.colors.warning)}>
              {improveCountLine(p, item)}
            </span>
            {before ? <span className="text-xs text-muted-foreground">{before}</span> : null}
          </p>
        </div>
      </div>
      <div className="mt-5 space-y-3.5 sm:pl-10">
        {item.criterion ? (
          <Field icon={BookOpen} label={p.coachImproveAsks}>
            <p className="text-sm leading-relaxed text-foreground/80">{item.criterion}</p>
          </Field>
        ) : null}
        <SlipFields
          reason={example?.reason ?? null}
          quote={example?.quote ?? null}
          advice={item.how}
          extra={
            example ? (
              <Link
                to={`/dashboard/memos/${example.memo_id}`}
                className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                {fill(p.coachImproveInCall, { date: dayLabel(example.observed_at, language) })}
                <ArrowRight aria-hidden className="h-3 w-3" />
              </Link>
            ) : null
          }
        />
      </div>
    </article>
  );
}

/** The steps of a call as coloured chips: not done in red, halfway in amber, or one green "Todo hecho". */
function SlipChips({ call }: { call: CoachCall }) {
  const { t } = useLanguage();
  const p = t.product;
  if (!call.applicable && !call.slips.length) {
    // A follow-up or a call cut short where no step applied: nothing was judged, so nothing is "done".
    return <p className="mt-1 text-[13px] text-muted-foreground">{p.coachCallNothingJudged}</p>;
  }
  const ordered = bySeverity(call.slips);
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1.5" data-testid="coach-call-slips">
      {/* Grey, so it never reads as one of the coloured step chips; the count carries the tone. */}
      <span className={cn(CHIP, THEME_TOKENS.colors.neutral)}>
        {p.coachCardSteps}
        <span className={cn("tabular-nums", TONE_TEXT[countTone(call.done, call.applicable)])}>
          {call.done}/{call.applicable}
        </span>
      </span>
      {call.meeting_agreed ? (
        <span className={cn(CHIP, THEME_TOKENS.colors.success)}>
          {p.coachCardMeeting} · {p.coachCardYes}
        </span>
      ) : null}
      {ordered.length ? (
        ordered.map((slip) => {
          const look = SLIP_LOOK[slip.state];
          const Icon = look.icon;
          return (
            <span key={slip.step_id} className={cn(CHIP, look.chip)} title={p[look.labelKey]}>
              <Icon aria-hidden className="h-3 w-3" strokeWidth={2} />
              <span className="sr-only">{p[look.labelKey]}: </span>
              {slip.label}
            </span>
          );
        })
      ) : (
        <span className={cn(CHIP, THEME_TOKENS.colors.success)}>
          <CircleCheck aria-hidden className="h-3 w-3" strokeWidth={2} />
          {p.coachCallAllDone}
        </span>
      )}
    </div>
  );
}

function SlipDetail({ slip }: { slip: CoachSlip }) {
  return (
    <li className="space-y-3 border-t border-border/50 py-5 first:border-t-0 first:pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[15px] font-semibold text-foreground">{slip.label}</span>
        <StatePill state={slip.state} />
      </div>
      <div className="space-y-3">
        <SlipFields reason={slip.reason} quote={slip.quote} advice={slip.advice} />
      </div>
    </li>
  );
}

/** One call of the record, as a row like Inicio's: what happened, steps as chips, and when.
 * A call with something to improve opens in place; one with nothing to improve opens the call. */
function CallRow({ call }: { call: CoachCall }) {
  const { t, language } = useLanguage();
  const p = t.product;
  const duration = durationLabel(p, call.duration_s);
  const body = (
    <>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[15px] leading-snug text-foreground">{cleanSummaryLine(call.summary_line)}</p>
        <SlipChips call={call} />
      </div>
      <div className="w-[5.5rem] shrink-0 text-right text-xs leading-tight tabular-nums text-muted-foreground">
        <span className="block text-[13px] text-foreground/85">{dayLabel(call.observed_at, language)}</span>
        <span className="mt-0.5 block text-[11.5px]">
          {timeLabel(call.observed_at, language)}
          {duration ? ` · ${duration}` : ""}
        </span>
      </div>
    </>
  );
  if (!call.slips.length) {
    return (
      <li>
        <Link to={`/dashboard/memos/${call.memo_id}`} className={`flex items-start gap-3.5 ${ROW}`} data-testid="coach-call">
          {body}
          <span className="w-4 shrink-0" aria-hidden />
        </Link>
      </li>
    );
  }
  return (
    <li data-testid="coach-call">
      <Collapsible>
        <CollapsibleTrigger className={`group flex w-full items-start gap-3.5 text-left data-[state=open]:bg-secondary/60 ${ROW}`}>
          {body}
          <ChevronDown size={16} strokeWidth={1.5} className="mt-1 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
        </CollapsibleTrigger>
        <CollapsibleContent className="px-3 pb-4">
          <ul>
            {bySeverity(call.slips).map((slip) => (
              <SlipDetail key={slip.step_id} slip={slip} />
            ))}
          </ul>
          <Link
            to={`/dashboard/memos/${call.memo_id}`}
            className="inline-flex items-center gap-1 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
          >
            {p.coachOpenCall}
            <ArrowRight aria-hidden className="h-3.5 w-3.5" />
          </Link>
        </CollapsibleContent>
      </Collapsible>
    </li>
  );
}

/** Coaching: what to improve first, then the record of the rep's calls, on one plane. Only the rep
 * against their own playbook, one interaction type at a time. */
export function CoachingCalls({ type, onType }: { type: string | null; onType: (type: string) => void }) {
  const { t } = useLanguage();
  const p = t.product;
  const query = useCoachCalls(type);
  if (query.isError) return <CoachError onRetry={() => void query.refetch()} />;
  if (!query.data) return <CoachLoading />;
  const data: CoachCalls = query.data;
  if (!data.type) return <CoachEmpty text={p.coachNoPlaybook} />;
  const name = (key: string, label: string | null) => label || p.pb2.typeLabels[key as keyof typeof p.pb2.typeLabels] || motionLabel(key, p.motions);
  const weeks = data.window_weeks;
  return (
    <div className="space-y-10" data-testid="coach-calls">
      {data.types.length > 1 ? (
        <div className="px-3">
          <Segmented
            value={data.type}
            onValueChange={onType}
            options={data.types.map((option) => ({ value: option.key, label: name(option.key, option.label) }))}
            aria-label={p.coachTypeLabel}
          />
        </div>
      ) : null}
      {/* Inicio's layout: headings and text sit 12px in, in line with the rows' content; a row's hover spans the page. */}
      <section aria-labelledby="coach-improve" className="space-y-3 px-3">
        <div className="space-y-0.5">
          <h2 id="coach-improve" className={THEME_TOKENS.typography.sectionTitle}>{p.coachImproveHeading}</h2>
          <p className={THEME_TOKENS.typography.capsLabel}>{fill(p.coachImproveWindow, { weeks, count: data.conversations })}</p>
        </div>
        {data.improve.length ? (
          <div>
            {data.improve.map((item, index) => (
              <ImproveItem key={item.step_id} item={item} weeks={weeks} index={index} />
            ))}
          </div>
        ) : (
          <p className={THEME_TOKENS.typography.body}>
            {data.conversations ? fill(p.coachImproveNone, { count: data.conversations }) : fill(p.coachImproveNoCalls, { weeks })}
          </p>
        )}
      </section>
      {data.calls.length ? (
        <section aria-labelledby="coach-calls-heading" className="space-y-2">
          <h2 id="coach-calls-heading" className={`px-3 ${THEME_TOKENS.typography.sectionTitle}`}>{p.coachCallsHeading}</h2>
          <ul className="space-y-0.5">
            {data.calls.map((call) => (
              <CallRow key={call.memo_id} call={call} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
