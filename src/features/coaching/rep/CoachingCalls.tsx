import { Link } from "react-router-dom";
import { ChevronDown } from "lucide-react";
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

function dateLine(iso: string | null, language: string, withTime = true): string {
  if (!iso) return "";
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  const locale = language === "EN" ? "en-GB" : "es-ES";
  const day = at.toLocaleDateString(locale, { weekday: "short", day: "numeric", month: "short" });
  return withTime ? `${day} · ${at.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })}` : day;
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
    <article className="space-y-3 border-t border-border/60 pt-4 first:border-t-0 first:pt-0" data-testid="coach-improve-item">
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
        <div className={`space-y-2 ${THEME_TOKENS.radius.control} bg-secondary/40 p-3.5`}>
          <p className={THEME_TOKENS.typography.capsLabel}>
            {fill(p.coachImproveInCall, { date: dateLine(item.example.observed_at, language, false) })}
            {" · "}
            <Link to={`/dashboard/memos/${item.example.memo_id}`} className="underline-offset-2 hover:underline">
              {p.coachOpenCall}
            </Link>
          </p>
          {item.example.reason ? <p className={THEME_TOKENS.typography.itemBody}>{item.example.reason}</p> : null}
          {item.example.quote ? <Quote text={item.example.quote} /> : null}
        </div>
      ) : null}
      {item.how ? <NextTime text={item.how} /> : null}
      {before ? <p className="text-xs text-muted-foreground">{before}</p> : null}
    </article>
  );
}

function SlipDetail({ slip }: { slip: CoachSlip }) {
  const { t } = useLanguage();
  const view = stateView(slip.state);
  return (
    <li className="space-y-1.5 border-t border-border/60 py-3 first:border-t-0">
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

/** "No hecho: A · B · Mejorable: C": which steps slipped, before opening the call. */
function SlipLine({ slips }: { slips: CoachSlip[] }) {
  const { t } = useLanguage();
  const p = t.product;
  const missing = slips.filter((slip) => slip.state === "missing").map((slip) => slip.label);
  const halfway = slips.filter((slip) => slip.state === "improvable").map((slip) => slip.label);
  return (
    <p className="text-[13px] text-muted-foreground" data-testid="coach-call-slips">
      {missing.length ? <><span className="text-destructive">{p.coachStateMissing}:</span> {missing.join(" · ")}</> : null}
      {missing.length && halfway.length ? " · " : null}
      {halfway.length ? <><span className="text-warning">{p.coachStateImprovable}:</span> {halfway.join(" · ")}</> : null}
    </p>
  );
}

/** A call with something to improve: closed it says when, how it ended, the steps done and which slipped;
 * open, each slip with what went wrong, the moment and what to try. */
function CallItem({ call }: { call: CoachCall }) {
  const { t, language } = useLanguage();
  const p = t.product;
  const duration = durationLabel(p, call.duration_s);
  return (
    <li className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`} data-testid="coach-call">
      <Collapsible>
        <CollapsibleTrigger className="group flex w-full items-start gap-4 p-5 text-left">
          <div className="min-w-0 flex-1 space-y-1">
            <p className={THEME_TOKENS.typography.capsLabel}>
              {dateLine(call.observed_at, language)}
              {duration ? ` · ${duration}` : ""}
            </p>
            <p className="line-clamp-2 text-[15px] leading-snug text-foreground">{cleanSummaryLine(call.summary_line)}</p>
            <p className="text-[13px] text-muted-foreground">
              {p.coachCardSteps}{" "}
              <span className={`tabular-nums ${TONE_TEXT[countTone(call.done, call.applicable)]}`}>
                {call.applicable ? `${call.done}/${call.applicable}` : "—"}
              </span>
              {/* Only a "yes": the meeting comes from what the rep declared, and no declaration is not a "no". */}
              {call.meeting_agreed ? <span className="text-success"> · {p.coachCardMeeting} · {p.coachCardYes}</span> : null}
            </p>
            <SlipLine slips={call.slips} />
          </div>
          <ChevronDown size={16} strokeWidth={1.5} className="mt-1 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
        </CollapsibleTrigger>
        <CollapsibleContent className="px-5 pb-4">
          <ul>
            {call.slips.map((slip) => (
              <SlipDetail key={slip.step_id} slip={slip} />
            ))}
          </ul>
          <Link to={`/dashboard/memos/${call.memo_id}`} className={THEME_TOKENS.interaction.quietAction}>
            {p.coachOpenCall} →
          </Link>
        </CollapsibleContent>
      </Collapsible>
    </li>
  );
}

/** Coaching → Mis llamadas: what to improve first, then every call with something to improve. Only the
 * rep against their own playbook, one interaction type at a time. */
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
    <div className="space-y-6" data-testid="coach-calls">
      {data.types.length > 1 ? (
        <Segmented
          value={data.type}
          onValueChange={onType}
          options={data.types.map((option) => ({ value: option.key, label: name(option.key, option.label) }))}
          aria-label={p.coachTypeLabel}
        />
      ) : null}
      <section aria-labelledby="coach-improve" className={`space-y-4 ${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 md:p-6`}>
        <div className="space-y-0.5">
          <h2 id="coach-improve" className={THEME_TOKENS.typography.sectionTitle}>{p.coachImproveHeading}</h2>
          <p className={THEME_TOKENS.typography.capsLabel}>{fill(p.coachImproveWindow, { weeks, count: data.conversations })}</p>
        </div>
        {data.improve.length ? (
          data.improve.map((item) => <ImproveItem key={item.step_id} item={item} weeks={weeks} />)
        ) : (
          <p className={THEME_TOKENS.typography.body}>
            {data.conversations ? fill(p.coachImproveNone, { count: data.conversations }) : fill(p.coachImproveNoCalls, { weeks })}
          </p>
        )}
      </section>
      {data.conversations ? (
        <section aria-labelledby="coach-calls-heading" className="space-y-3">
          <h2 id="coach-calls-heading" className={THEME_TOKENS.typography.sectionTitle}>{p.coachCallsHeading}</h2>
          {data.calls.length ? (
            <ul className="space-y-3">
              {data.calls.map((call) => (
                <CallItem key={call.memo_id} call={call} />
              ))}
            </ul>
          ) : (
            <p className={THEME_TOKENS.typography.body}>{fill(p.coachCallsNone, { weeks })}</p>
          )}
          {data.calls_clean ? (
            <p className="text-xs text-muted-foreground">{fill(p.coachCallsClean, { count: data.calls_clean })}</p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
