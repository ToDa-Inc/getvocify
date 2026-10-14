import { Link } from "react-router-dom";
import { ArrowUpRight, ChevronDown, Lightbulb } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Segmented } from "@/components/ui/segmented";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import {
  cleanSummaryLine,
  durationLabel,
  fill,
  type CoachCall,
  type CoachCalls,
  type CoachSlip,
} from "@/lib/rep-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { CoachEmpty, CoachError, CoachLoading } from "./CoachingState";
import { useCoachCalls } from "./useRepCoaching";
import { ImproveTables } from "./ImproveTables";

/** Colour only where it means something: red not done, amber halfway, green done. */
const STATE_TEXT = { missing: "text-destructive", improvable: "text-warning" } as const;

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

function SectionHead({ id, title, meta }: { id: string; title: string; meta?: string }) {
  return (
    <div className="space-y-0.5">
      <h2 id={id} className={THEME_TOKENS.typography.sectionTitle}>{title}</h2>
      {meta ? <p className="text-[13px] text-muted-foreground">{meta}</p> : null}
    </div>
  );
}

/** What was said in the call: a quiet bubble. */
function Moment({ quote }: { quote: string }) {
  return (
    <blockquote className={`${THEME_TOKENS.radius.control} bg-secondary/70 px-4 py-3 text-[14.5px] italic leading-relaxed text-foreground/85`}>
      «{quote}»
    </blockquote>
  );
}

/** What to try next time, whole: the one line to take into the next call. */
function NextTime({ text }: { text: string }) {
  return (
    <div className={`flex gap-2.5 ${THEME_TOKENS.radius.control} bg-success/10 px-4 py-3`}>
      <Lightbulb aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-success" strokeWidth={1.75} />
      <p className="text-[14.5px] leading-relaxed text-foreground">{text}</p>
    </div>
  );
}

/** The steps of one call at a glance: one segment each, green done, amber halfway, red not done. */
function StepMeter({ call }: { call: CoachCall }) {
  const { t } = useLanguage();
  const p = t.product;
  if (!call.applicable) return <span className="text-xs text-muted-foreground">{p.coachCallNothingJudged}</span>;
  const halfway = call.slips.filter((slip) => slip.state === "improvable").length;
  const missing = call.slips.filter((slip) => slip.state === "missing").length;
  const segments = [
    ...Array(Math.max(0, call.done - halfway)).fill("bg-success/70"),
    ...Array(halfway).fill("bg-warning/80"),
    ...Array(missing).fill("bg-destructive/70"),
  ];
  return (
    <span className="flex items-center gap-2" role="img" aria-label={`${p.coachCardSteps} ${call.done}/${call.applicable}`}>
      <span className="flex w-24 gap-0.5">
        {segments.map((tone, index) => (
          <span key={index} className={cn("h-1.5 flex-1 rounded-full", tone)} />
        ))}
      </span>
      <span className="text-xs tabular-nums text-muted-foreground">
        {call.done}/{call.applicable}
      </span>
      {call.meeting_agreed ? <span className="text-xs text-success">{p.coachCardMeeting} · {p.coachCardYes}</span> : null}
    </span>
  );
}

function SlipDetail({ slip }: { slip: CoachSlip }) {
  const { t } = useLanguage();
  const p = t.product;
  return (
    <li className="space-y-3 py-4">
      <div className="flex items-baseline gap-2">
        <h4 className="text-[15px] font-medium text-foreground">{slip.label}</h4>
        <span className={cn("text-xs", STATE_TEXT[slip.state])}>
          {slip.state === "missing" ? p.coachStateMissing : p.coachStateImprovable}
        </span>
      </div>
      {slip.reason ? <p className="text-[14.5px] leading-relaxed text-muted-foreground">{slip.reason}</p> : null}
      {slip.quote ? <Moment quote={slip.quote} /> : null}
      {slip.advice ? <NextTime text={slip.advice} /> : null}
    </li>
  );
}

/** One call of the record: what happened, its steps as a meter, and when. One with something to improve
 * opens in place; one with nothing to improve opens the call. */
function CallRow({ call }: { call: CoachCall }) {
  const { t, language } = useLanguage();
  const p = t.product;
  const duration = durationLabel(p, call.duration_s);
  const body = (
    <>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[15px] leading-snug text-foreground">{cleanSummaryLine(call.summary_line)}</p>
        <div className="mt-1.5">
          <StepMeter call={call} />
        </div>
      </div>
      <div className="w-[5.5rem] shrink-0 text-right leading-tight tabular-nums">
        <span className="block text-[13px] text-foreground/85">{dayLabel(call.observed_at, language)}</span>
        <span className="mt-0.5 block text-[11.5px] text-muted-foreground">
          {timeLabel(call.observed_at, language)}
          {duration ? ` · ${duration}` : ""}
        </span>
      </div>
    </>
  );
  const row = `flex w-full items-center gap-4 rounded-lg px-3 py-3.5 text-left ${THEME_TOKENS.interaction.rowHover}`;
  if (!call.slips.length) {
    return (
      <li>
        <Link to={`/dashboard/memos/${call.memo_id}`} className={row} data-testid="coach-call">
          {body}
          <span className="w-4 shrink-0" aria-hidden />
        </Link>
      </li>
    );
  }
  const ordered = [...call.slips].sort((a, b) => Number(a.state !== "missing") - Number(b.state !== "missing"));
  return (
    <li data-testid="coach-call">
      <Collapsible>
        <CollapsibleTrigger className={`group ${row} data-[state=open]:bg-secondary/60`}>
          {body}
          <ChevronDown size={16} strokeWidth={1.5} className="shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
        </CollapsibleTrigger>
        <CollapsibleContent className="ml-3 border-l border-border/70 pb-3 pl-5 pr-3">
          <ul className="divide-y divide-border/50">
            {ordered.map((slip) => (
              <SlipDetail key={slip.step_id} slip={slip} />
            ))}
          </ul>
          <Link
            to={`/dashboard/memos/${call.memo_id}`}
            className="mt-1 inline-flex items-center gap-1 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
          >
            {p.coachOpenCall}
            <ArrowUpRight aria-hidden className="h-3.5 w-3.5" />
          </Link>
        </CollapsibleContent>
      </Collapsible>
    </li>
  );
}

/** Coaching: what to improve next to the rep's steps, then the record of their calls. Only the rep
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
    <div className="space-y-14" data-testid="coach-calls">
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
      <section aria-labelledby="coach-improve" className="space-y-5 px-3">
        <SectionHead id="coach-improve" title={p.coachImproveHeading} meta={fill(p.coachImproveWindow, { weeks, count: data.conversations })} />
        {!data.conversations ? (
          <p className="text-[14.5px] text-muted-foreground">{fill(p.coachImproveNoCalls, { weeks })}</p>
        ) : data.slipped_steps && data.objections ? (
          <ImproveTables steps={data.slipped_steps} objections={data.objections} />
        ) : (
          // A backend older than the tables (the web deploys before it): never say "nothing slipped".
          <p className="text-[14.5px] text-muted-foreground">{p.coachImproveUpdating}</p>
        )}
      </section>
      {data.calls.length ? (
        <section aria-labelledby="coach-calls-heading" className="space-y-2">
          <div className="px-3">
            <SectionHead id="coach-calls-heading" title={p.coachCallsHeading} />
          </div>
          <ul className="divide-y divide-border/50">
            {data.calls.map((call) => (
              <CallRow key={call.memo_id} call={call} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
