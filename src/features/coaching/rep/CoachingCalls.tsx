import { Link } from "react-router-dom";
import { ArrowRight, ChevronDown } from "lucide-react";
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
  stateView,
  type CoachCall,
  type CoachCalls,
  type CoachImprove,
  type CoachSlip,
} from "@/lib/rep-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { CoachEmpty, CoachError, CoachLoading } from "./CoachingState";
import { useCoachCalls } from "./useRepCoaching";

const TONE_TEXT = { success: "text-success", warning: "text-warning", destructive: "text-destructive", muted: "text-foreground" } as const;
const ROW = "rounded-xl px-3 py-2.5 transition-colors duration-150 hover:bg-secondary/60 motion-reduce:transition-none";

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

/** The moment of the call, as said. */
function Quote({ text }: { text: string }) {
  return <blockquote className="border-l-2 border-border pl-3 text-sm italic text-foreground/80">«{text}»</blockquote>;
}

/** What to try next time: the one line a rep should take into the next call. */
function NextTime({ text }: { text: string }) {
  const { t } = useLanguage();
  return (
    <p className="text-sm text-foreground">
      <span className="font-medium text-success">{t.product.coachImproveHow}:</span> {text}
    </p>
  );
}

/** One of the one or two steps slipped most: what the playbook asks, a call that shows it, how to do it. */
function ImproveItem({ item, weeks }: { item: CoachImprove; weeks: number }) {
  const { t, language } = useLanguage();
  const p = t.product;
  const before = improveBeforeLine(p, item, weeks);
  return (
    <article className="border-t border-border/60 py-5 first:border-t-0 first:pt-1" data-testid="coach-improve-item">
      <div className="space-y-3">
        <div className="space-y-0.5">
          <h3 className={THEME_TOKENS.typography.itemTitle}>{item.label}</h3>
          <p className="text-sm text-warning">{improveCountLine(p, item)}</p>
        </div>
        {item.criterion ? (
          <div>
            <p className={THEME_TOKENS.typography.fieldLabel}>{p.coachImproveAsks}</p>
            <p className={THEME_TOKENS.typography.itemBody}>{item.criterion}</p>
          </div>
        ) : null}
        {item.example ? (
          <div className="space-y-1.5">
            <p className={THEME_TOKENS.typography.fieldLabel}>
              {fill(p.coachImproveInCall, { date: dayLabel(item.example.observed_at, language) })}
              {" · "}
              <Link to={`/dashboard/memos/${item.example.memo_id}`} className="underline-offset-2 hover:text-foreground hover:underline">
                {p.coachOpenCall}
              </Link>
            </p>
            {item.example.reason ? <p className={THEME_TOKENS.typography.itemBody}>{item.example.reason}</p> : null}
            {item.example.quote ? <Quote text={item.example.quote} /> : null}
          </div>
        ) : null}
        {item.how ? <NextTime text={item.how} /> : null}
        {before ? <p className="text-xs text-muted-foreground">{before}</p> : null}
      </div>
    </article>
  );
}

/** "No hecho: A · B · Mejorable: C", or "Todo hecho": what slipped, before opening the call. */
function SlipLine({ slips }: { slips: CoachSlip[] }) {
  const { t } = useLanguage();
  const p = t.product;
  if (!slips.length) return <span className="text-success">{p.coachCallAllDone}</span>;
  const missing = slips.filter((slip) => slip.state === "missing").map((slip) => slip.label);
  const halfway = slips.filter((slip) => slip.state === "improvable").map((slip) => slip.label);
  return (
    <span data-testid="coach-call-slips">
      {missing.length ? <><span className="text-destructive">{p.coachStateMissing}:</span> {missing.join(" · ")}</> : null}
      {missing.length && halfway.length ? " · " : null}
      {halfway.length ? <><span className="text-warning">{p.coachStateImprovable}:</span> {halfway.join(" · ")}</> : null}
    </span>
  );
}

function SlipDetail({ slip }: { slip: CoachSlip }) {
  const { t } = useLanguage();
  const view = stateView(slip.state);
  return (
    <li className="space-y-1.5 py-2.5">
      <p className="text-sm">
        <span className="font-medium text-foreground">{slip.label}</span>
        <span className={`ml-2 text-xs ${slip.state === "missing" ? "text-destructive" : "text-warning"}`}>
          {String(t.product[view.labelKey])}
        </span>
      </p>
      {slip.reason ? <p className={THEME_TOKENS.typography.itemBody}>{slip.reason}</p> : null}
      {slip.quote ? <Quote text={slip.quote} /> : null}
      {slip.advice ? <NextTime text={slip.advice} /> : null}
    </li>
  );
}

/** One call of the record, as a row like Inicio's: what happened, steps done and what slipped, and when.
 * A call with something to improve opens in place; one with nothing to improve opens the call. */
function CallRow({ call }: { call: CoachCall }) {
  const { t, language } = useLanguage();
  const p = t.product;
  const duration = durationLabel(p, call.duration_s);
  const body = (
    <>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[15px] leading-snug text-foreground">{cleanSummaryLine(call.summary_line)}</p>
        {!call.applicable && !call.slips.length ? (
          // A follow-up or a call cut short where no step applied: nothing was judged, so nothing is "done".
          <p className="mt-0.5 text-[13px] text-muted-foreground">{p.coachCallNothingJudged}</p>
        ) : (
          <p className="mt-0.5 line-clamp-2 text-[13px] text-muted-foreground">
            {p.coachCardSteps}{" "}
            <span className={`tabular-nums ${TONE_TEXT[countTone(call.done, call.applicable)]}`}>
              {call.applicable ? `${call.done}/${call.applicable}` : "—"}
            </span>
            {/* Only a "yes": the meeting comes from what the rep declared, and no declaration is not a "no". */}
            {call.meeting_agreed ? <span className="text-success"> · {p.coachCardMeeting} · {p.coachCardYes}</span> : null}
            {" · "}
            <SlipLine slips={call.slips} />
          </p>
        )}
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
        <CollapsibleTrigger className={`group flex w-full items-start gap-3.5 text-left ${ROW}`}>
          {body}
          <ChevronDown size={16} strokeWidth={1.5} className="mt-1 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
        </CollapsibleTrigger>
        <CollapsibleContent className="ml-3 border-l border-border/60 pb-2 pl-4">
          <ul>
            {call.slips.map((slip) => (
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
            {data.improve.map((item) => (
              <ImproveItem key={item.step_id} item={item} weeks={weeks} />
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
