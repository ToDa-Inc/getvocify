import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, ChevronDown, Lightbulb } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import type { CoachObjectionBreakdown, CoachSlippedStep } from "@/lib/rep-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

// One row of either table: how many times it went wrong out of how many, and when it last did.
type Row = { id: string; title: string; bad: number; half: number; of: number; latest: string | null };

// name · times · bar · latest · chevron: narrow enough for two tables side by side.
const GRID = "grid grid-cols-[minmax(0,1fr)_3.25rem_4rem_4.75rem_1rem] items-center gap-3";

function dayLabel(iso: string, language: string, weekday = true) {
  return new Date(iso).toLocaleDateString(language === "EN" ? "en-GB" : "es-ES", {
    ...(weekday ? { weekday: "short" as const } : {}),
    day: "numeric",
    month: "short",
  });
}

function CallLink({ memoId, at }: { memoId: string; at: string }) {
  const { language } = useLanguage();
  return (
    <Link to={`/dashboard/memos/${memoId}`} className="inline-flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground">
      {dayLabel(at, language)}
      <ArrowUpRight aria-hidden className="h-3 w-3" />
    </Link>
  );
}

/** "4/5" in red, or in amber when it was only ever done halfway. */
function Count({ row }: { row: Row }) {
  const halfwayOnly = !row.bad && row.half > 0;
  return (
    <span className={cn("text-sm font-medium tabular-nums", halfwayOnly ? "text-warning" : row.bad ? "text-destructive" : "text-success")}>
      {halfwayOnly ? row.half : row.bad}
      <span className="font-normal text-muted-foreground/70">/{row.of}</span>
    </span>
  );
}

/** What to do next time, whole: the one line to take into the next call. */
function NextTime({ text }: { text: string }) {
  return (
    <div className={`flex gap-2.5 ${THEME_TOKENS.radius.control} bg-success/10 px-4 py-3`}>
      <Lightbulb aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-success" strokeWidth={1.75} />
      <p className="text-[14.5px] leading-relaxed text-foreground">{text}</p>
    </div>
  );
}

const TAG_TONE = { bad: "text-destructive", half: "text-warning", good: "text-success" } as const;

function Tag({ tone, children }: { tone: keyof typeof TAG_TONE; children: string }) {
  return <span className={cn("text-xs font-medium", TAG_TONE[tone])}>{children}</span>;
}

/** A table that opens in place: the rows say what went wrong how often; a row shows next time and every call. */
function Table({
  id,
  title,
  rows,
  empty,
  detail,
}: {
  id: string;
  title: string;
  rows: Row[];
  empty: string;
  detail: (rowId: string) => ReactNode;
}) {
  const { t, language } = useLanguage();
  const p = t.product;
  const [open, setOpen] = useState<string | null>(null);
  return (
    <section aria-labelledby={id} className="min-w-0">
      <div className={`${GRID} border-b border-border/60 px-3 pb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground`}>
        <h3 id={id} className="truncate">
          {title} · {rows.length}
        </h3>
        <span className="text-right">{p.coachTableTimes}</span>
        <span />
        <span className="text-right">{p.coachTableLatest}</span>
        <span />
      </div>
      {rows.length ? (
        <ul className="divide-y divide-border/40">
          {rows.map((row) => {
            const expanded = open === row.id;
            const share = row.of ? (row.bad || row.half) / row.of : 0;
            return (
              <li key={row.id}>
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => setOpen(expanded ? null : row.id)}
                  className={cn(`${GRID} w-full rounded-lg px-3 py-2.5 text-left`, THEME_TOKENS.interaction.rowHover, expanded && "bg-secondary/60")}
                >
                  <span className="truncate text-sm text-foreground" title={row.title}>
                    {row.title}
                  </span>
                  <span className="text-right">
                    <Count row={row} />
                  </span>
                  <span className="h-1.5 overflow-hidden rounded-full bg-secondary">
                    <span
                      className={cn("block h-full rounded-full", row.bad ? "bg-destructive/60" : "bg-warning/70")}
                      style={{ width: `${Math.round(share * 100)}%` }}
                    />
                  </span>
                  <span className="text-right text-xs tabular-nums text-muted-foreground">
                    {row.latest ? dayLabel(row.latest, language, false) : ""}
                  </span>
                  <ChevronDown aria-hidden className={cn("h-4 w-4 text-muted-foreground transition-transform", expanded && "rotate-180")} />
                </button>
                {expanded ? <div className="space-y-4 px-3 pb-5 pt-2">{detail(row.id)}</div> : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="px-3 py-3 text-[14.5px] text-muted-foreground">{empty}</p>
      )}
    </section>
  );
}

function StepDetail({ step }: { step: CoachSlippedStep }) {
  const { t } = useLanguage();
  const p = t.product;
  // This rep's own advice from the latest call that has one; else the playbook's example phrase.
  const how = step.occurrences.find((occurrence) => occurrence.advice)?.advice ?? step.example;
  return (
    <>
      {how ? <NextTime text={how} /> : null}
      <ol className="space-y-4 border-l border-border/70 pl-4">
        {step.occurrences.map((occurrence) => (
          <li key={occurrence.memo_id} className="space-y-1.5">
            <div className="flex items-center gap-2">
              <Tag tone={occurrence.state === "missing" ? "bad" : "half"}>
                {occurrence.state === "missing" ? p.coachStateMissing : p.coachStateImprovable}
              </Tag>
              <CallLink memoId={occurrence.memo_id} at={occurrence.observed_at} />
            </div>
            {occurrence.reason ? <p className="text-[14.5px] leading-relaxed text-foreground">{occurrence.reason}</p> : null}
            {occurrence.quote ? <p className="text-[14px] italic leading-relaxed text-muted-foreground">«{occurrence.quote}»</p> : null}
          </li>
        ))}
      </ol>
    </>
  );
}

function ObjectionDetail({ objection }: { objection: CoachObjectionBreakdown }) {
  const { t } = useLanguage();
  const p = t.product;
  const status = { open: p.coachObjectionOpen, resolved: p.coachObjectionResolved, unknown: p.coachObjectionUnknown };
  return (
    <>
      {objection.how ? <NextTime text={objection.how} /> : null}
      <ol className="space-y-4 border-l border-border/70 pl-4">
        {objection.occurrences.map((occurrence, index) => (
          <li key={`${occurrence.memo_id}-${index}`} className="space-y-1.5">
            <div className="flex items-center gap-2">
              <Tag tone={occurrence.resolution === "resolved" ? "good" : occurrence.resolution === "open" ? "bad" : "half"}>
                {status[occurrence.resolution]}
              </Tag>
              <CallLink memoId={occurrence.memo_id} at={occurrence.observed_at} />
            </div>
            {occurrence.quote ? <p className="text-[14.5px] italic leading-relaxed text-foreground">«{occurrence.quote}»</p> : null}
            <p className="text-[13.5px] leading-relaxed text-muted-foreground">
              {occurrence.response ? `${p.coachYouReplied}: «${occurrence.response}»` : p.coachNoReply}
            </p>
          </li>
        ))}
      </ol>
    </>
  );
}

/** "En qué mejorar": every step slipped on and every objection given in the last weeks, as two tables
 * side by side (stacked on a phone). Little text by default; a row opens with everything, uncut. */
export function ImproveTables({ steps, objections }: { steps: CoachSlippedStep[]; objections: CoachObjectionBreakdown[] }) {
  const { t } = useLanguage();
  const p = t.product;
  const categories = p.playbookObjectionCategories as Record<string, string>;
  const stepRows: Row[] = steps.map((step) => ({
    id: step.step_id,
    title: step.label,
    bad: step.missing,
    half: step.improvable,
    of: step.applicable,
    latest: step.occurrences[0]?.observed_at ?? null,
  }));
  const objectionRows: Row[] = objections.map((objection) => ({
    id: objection.key,
    title: objection.label || categories[objection.category] || objection.category,
    bad: objection.open,
    half: 0,
    of: objection.total,
    latest: objection.occurrences[0]?.observed_at ?? null,
  }));
  return (
    <div className="-mx-3 grid gap-10 lg:grid-cols-2 lg:gap-8">
      <Table
        id="coach-improve-steps"
        title={p.coachTableSteps}
        rows={stepRows}
        empty={p.coachNothingSlipped}
        detail={(id) => {
          const step = steps.find((candidate) => candidate.step_id === id);
          return step ? <StepDetail step={step} /> : null;
        }}
      />
      <Table
        id="coach-improve-objections"
        title={p.coachTableObjections}
        rows={objectionRows}
        empty={p.coachNoObjections}
        detail={(id) => {
          const objection = objections.find((candidate) => candidate.key === id);
          return objection ? <ObjectionDetail objection={objection} /> : null;
        }}
      />
    </div>
  );
}
