import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { ArrowUpRight, ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useLanguage } from "@/lib/i18n";
import {
  cleanSummaryLine,
  durationLabel,
  fill,
  type CoachCall,
  type CoachCalls,
} from "@/lib/rep-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { ImproveTables } from "./ImproveTables";
import { OccurrencePager, type Moment } from "./OccurrencePager";

/** Past a screenful the record pages instead of growing the page (the app's list size). */
const CALLS_PER_PAGE = 20;

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

/** The steps of one call at a glance: one segment each, green done, amber halfway, red not done. */
function StepMeter({ call }: { call: CoachCall }) {
  const { t } = useLanguage();
  const p = t.product;
  if (!call.applicable) {
    const count = call.objections?.length ?? 0;
    return (
      <span className="text-xs text-muted-foreground">
        {p.coachCallNothingJudged}
        {count ? ` · ${count} ${count === 1 ? p.coachObjectionOne : p.coachObjectionMany}` : ""}
      </span>
    );
  }
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

/** One call opened: each thing to improve in it (a step slipped on, an objection given), one moment each,
 * with the line to say instead. The worst first. */
function CallDetail({ call, type }: { call: CoachCall; type: string }) {
  const { t } = useLanguage();
  const p = t.product;
  const categories = p.playbookObjectionCategories as Record<string, string>;
  const slips = [...call.slips].sort((a, b) => Number(a.state !== "missing") - Number(b.state !== "missing"));
  const objections = [...(call.objections ?? [])].sort((a, b) => Number(a.resolution === "resolved") - Number(b.resolution === "resolved"));
  const at = call.observed_at ?? "";
  return (
    <div className="space-y-5 py-3">
      {slips.map((slip) => {
        const moment: Moment = { memo_id: call.memo_id, observed_at: at, tone: slip.state === "missing" ? "bad" : "half", quote: slip.quote, response: null, reason: slip.reason, advice: slip.advice };
        return (
          <section key={slip.step_id} className="space-y-2">
            <h4 className="text-[15px] font-medium text-foreground">{slip.label}</h4>
            <OccurrencePager type={type} kind="step" itemKey={slip.step_id} how={null} moments={[moment]} />
          </section>
        );
      })}
      {objections.map((objection, index) => {
        const moment: Moment = {
          memo_id: call.memo_id, observed_at: at, tone: objection.resolution === "resolved" ? "good" : objection.resolution === "open" ? "bad" : "unknown",
          quote: objection.quote, response: objection.response, reason: null, advice: null,
        };
        return (
          <section key={`${objection.key}-${index}`} className="space-y-2">
            <h4 className="text-[15px] font-medium text-foreground">{objection.label || categories[objection.category] || objection.category}</h4>
            <OccurrencePager type={type} kind="objection" itemKey={objection.key} how={objection.how} moments={[moment]} />
          </section>
        );
      })}
    </div>
  );
}

/** One call of the record: what happened, its steps as a meter, and when. One with something to improve
 * opens in place; one with nothing to improve opens the call. */
function CallRow({ call, type }: { call: CoachCall; type: string }) {
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
  const hasDetail = call.slips.length > 0 || (call.objections?.length ?? 0) > 0;
  if (!hasDetail) {
    return (
      <li>
        <Link to={`/dashboard/memos/${call.memo_id}`} className={row} data-testid="coach-call">
          {body}
          <span className="w-4 shrink-0" aria-hidden />
        </Link>
      </li>
    );
  }
  return (
    <li data-testid="coach-call">
      <Collapsible>
        <CollapsibleTrigger className={`group ${row} data-[state=open]:bg-secondary/60`}>
          {body}
          <ChevronDown size={16} strokeWidth={1.5} className="shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
        </CollapsibleTrigger>
        <CollapsibleContent className="ml-3 border-l border-border/70 pb-3 pl-5 pr-3">
          <CallDetail call={call} type={type} />
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

/** Progreso: what to improve (steps and objections), then the record of the rep's calls. Only the rep
 * against their own playbook; the type is the page's dropdown, so this only reads what it is given. */
export function CoachingCalls({ data }: { data: CoachCalls }) {
  const { t } = useLanguage();
  const p = t.product;
  const weeks = data.window_weeks;
  const [page, setPage] = useState(0);
  const pages = Math.ceil(data.calls.length / CALLS_PER_PAGE);
  const shown = data.calls.slice(page * CALLS_PER_PAGE, (page + 1) * CALLS_PER_PAGE);
  return (
    <div className="space-y-14" data-testid="coach-calls">
      <section aria-labelledby="coach-improve" className="space-y-5 px-3">
        <SectionHead id="coach-improve" title={p.coachImproveHeading} meta={fill(p.coachImproveWindow, { weeks, count: data.conversations })} />
        {!data.conversations ? (
          <p className="text-[14.5px] text-muted-foreground">{fill(p.coachImproveNoCalls, { weeks })}</p>
        ) : data.slipped_steps && data.objections ? (
          <ImproveTables type={data.type ?? ""} steps={data.slipped_steps} objections={data.objections} />
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
            {shown.map((call) => (
              <CallRow key={call.memo_id} call={call} type={data.type ?? ""} />
            ))}
          </ul>
          {pages > 1 ? (
            <nav aria-label={p.coachCallsHeading} className="flex items-center justify-center gap-3 pt-3 text-[13px] tabular-nums text-muted-foreground">
              <Button type="button" variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>
                <ChevronLeft aria-hidden />
                {p.coachPrevious}
              </Button>
              <span>{page + 1}/{pages}</span>
              <Button type="button" variant="outline" size="sm" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>
                {p.coachNext}
                <ChevronRight aria-hidden />
              </Button>
            </nav>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
