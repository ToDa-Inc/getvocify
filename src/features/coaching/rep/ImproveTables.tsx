import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, ChevronDown, Lightbulb } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import type { CoachObjectionBreakdown, CoachSlippedStep } from "@/lib/rep-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

// One row of either table: how many of the times it came up went well, half way, unclear or badly.
type Row = { id: string; title: string; good: number; half: number; unknown: number; bad: number; of: number };

// name · outcome bar · done count · chevron: narrow enough for two tables side by side.
const GRID = "grid grid-cols-[minmax(0,1fr)_5rem_2.75rem_1rem] items-center gap-3";
// The worst few first; the rest one click away, so twelve objections never push the calls off the page.
const VISIBLE_ROWS = 5;

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

/** Where every time it came up ended: green went well, amber half way, grey unclear, red not. The bar
 * is the whole story, so the row needs no colour on the number. */
function OutcomeBar({ row, label }: { row: Row; label: string }) {
  const segments = [
    ["bg-success/70", row.good],
    ["bg-warning/80", row.half],
    ["bg-muted-foreground/30", row.unknown],
    ["bg-destructive/70", row.bad],
  ] as const;
  return (
    <span className="flex h-1.5 gap-px overflow-hidden rounded-full bg-secondary" role="img" aria-label={label}>
      {segments.map(([tone, count]) =>
        count ? <span key={tone} className={tone} style={{ flexGrow: count, flexBasis: 0 }} /> : null,
      )}
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

/** A table that opens in place: each row says how often it went well, a row shows next time and every call. */
function Table({
  id,
  title,
  column,
  rows,
  empty,
  detail,
}: {
  id: string;
  title: string;
  /** What the number counts, as a good thing: "Hecho", "Resueltas". */
  column: string;
  rows: Row[];
  empty: string;
  detail: (rowId: string) => ReactNode;
}) {
  const { t } = useLanguage();
  const p = t.product;
  const [open, setOpen] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, VISIBLE_ROWS);
  const hidden = rows.length - shown.length;
  return (
    <section aria-labelledby={id} className="min-w-0">
      <div className={`${GRID} border-b border-border/60 px-3 pb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground`}>
        <h3 id={id} className="truncate">
          {title} · {rows.length}
        </h3>
        <span />
        <span className="text-right normal-case tracking-normal">{column}</span>
        <span />
      </div>
      {rows.length ? (
        <>
          <ul className="divide-y divide-border/40">
            {shown.map((row) => {
              const expanded = open === row.id;
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
                    <OutcomeBar row={row} label={`${row.title}: ${row.good}/${row.of}`} />
                    <span className="text-right text-sm font-medium tabular-nums text-foreground">
                      {row.good}
                      <span className="font-normal text-muted-foreground/70">/{row.of}</span>
                    </span>
                    <ChevronDown aria-hidden className={cn("h-4 w-4 text-muted-foreground transition-transform", expanded && "rotate-180")} />
                  </button>
                  {expanded ? <div className="space-y-4 px-3 pb-5 pt-2">{detail(row.id)}</div> : null}
                </li>
              );
            })}
          </ul>
          {rows.length > VISIBLE_ROWS ? (
            <Button type="button" variant="quiet" size="text" className="mt-1 px-3" onClick={() => setAll(!all)}>
              <ChevronDown aria-hidden className={cn("h-3.5 w-3.5 transition-transform", all && "rotate-180")} strokeWidth={1.5} />
              {all ? p.coachShowLess : p.coachShowMore.replace("{count}", String(hidden))}
            </Button>
          ) : null}
        </>
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
    // A step done halfway counts as done in the backend's totals, so only the rest is "well".
    good: Math.max(0, step.applicable - step.missing - step.improvable),
    half: step.improvable,
    unknown: 0,
    bad: step.missing,
    of: step.applicable,
  }));
  const objectionRows: Row[] = objections.map((objection) => ({
    id: objection.key,
    title: objection.label || categories[objection.category] || objection.category,
    good: objection.resolved,
    half: 0,
    unknown: Math.max(0, objection.total - objection.open - objection.resolved),
    bad: objection.open,
    of: objection.total,
  }));
  return (
    <div className="-mx-3 grid gap-10 lg:grid-cols-2 lg:gap-8">
      <Table
        id="coach-improve-steps"
        title={p.coachTableSteps}
        column={p.coachColDone}
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
        column={p.coachColResolved}
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
