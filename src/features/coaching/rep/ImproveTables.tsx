import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { afterTone, noObjectionsKey, readByAfter, tableObjections, UNANSWERED_KEY, type CoachObjectionBreakdown, type CoachSlippedStep } from "@/lib/rep-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { Bubble, OccurrencePager, type Moment } from "./OccurrencePager";

// One row of either table: how many of the times it came up went well, half way, unclear or badly.
type Row = { id: string; title: string; good: number; half: number; unknown: number; bad: number; of: number; /** A group rather than one item: lighter. */ group?: boolean };

// name · outcome bar · done count · chevron: narrow enough for two tables side by side.
const GRID = "grid grid-cols-[minmax(0,1fr)_5rem_2.75rem_1rem] items-center gap-3";
// The worst few first; the rest one click away, so twelve objections never push the calls off the page.
const VISIBLE_ROWS = 5;

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
                    <span className={cn("truncate text-sm", row.group ? "text-muted-foreground" : "text-foreground")} title={row.title}>
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

function StepDetail({ step, type }: { step: CoachSlippedStep; type: string }) {
  const moments: Moment[] = step.occurrences.map((o) => ({
    memo_id: o.memo_id, observed_at: o.observed_at, tone: o.state === "missing" ? "bad" : o.state === "done" ? "good" : "half", quote: o.quote, response: null, reason: o.reason, advice: o.advice,
  }));
  return <OccurrencePager key={step.step_id} type={type} kind="step" itemKey={step.step_id} how={step.example} moments={moments} />;
}

/** What colleagues replied to this objection when the call moved on: their words, to learn from (no link to their call). */
function Worked({ worked }: { worked: NonNullable<CoachObjectionBreakdown["worked"]> }) {
  const { t } = useLanguage();
  const p = t.product;
  if (!worked.length) return null;
  return (
    <section className="space-y-3 border-t border-border/60 pt-4">
      <h4 className="text-[13px] font-medium text-muted-foreground">{p.coachWorkedTitle}</h4>
      {worked.map((example, index) => (
        <div key={index} className="space-y-2">
          {example.quote ? <Bubble kind="prospect" caption={p.coachProspectSaid}>{example.quote}</Bubble> : null}
          {example.response ? <Bubble kind="better" caption={p.coachColleagueReplied}>{example.response}</Bubble> : null}
          {example.after_quote ? <Bubble kind="prospect" caption={p.coachTheyThenSaid}>{example.after_quote}</Bubble> : null}
        </div>
      ))}
    </section>
  );
}

function ObjectionDetail({ objection, type }: { objection: CoachObjectionBreakdown; type: string }) {
  const moments: Moment[] = objection.occurrences.map((o) => ({
    memo_id: o.memo_id, observed_at: o.observed_at, tone: afterTone(o.after, o.resolution), quote: o.quote, response: o.response, reason: null, advice: null,
    after: o.after ?? null, afterQuote: o.after_quote ?? null,
  }));
  return (
    <>
      <OccurrencePager key={objection.key} type={type} kind="objection" itemKey={objection.key} how={objection.how} moments={moments} />
      <Worked worked={objection.worked ?? []} />
    </>
  );
}

/** "En qué mejorar": every step slipped on and every objection given in the last weeks, as two tables
 * side by side (stacked on a phone). Little text by default; a row opens with everything, uncut. */
export function ImproveTables({ type, steps, objections }: { type: string; steps: CoachSlippedStep[]; objections: CoachObjectionBreakdown[] }) {
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
  const listed = tableObjections(objections);
  // Read by what followed each reply (C04 v10) once any row has it; calls read before keep "resolved".
  const byAfter = listed.some(readByAfter);
  const objectionRows: Row[] = listed.map((objection) => {
    const group = objection.key === UNANSWERED_KEY;
    const title = group ? p.coachUnanswered : objection.label || categories[objection.category] || objection.category;
    if (byAfter) {
      const advanced = objection.advanced ?? 0, stalled = objection.stalled ?? 0, ended = objection.ended ?? 0;
      return { id: objection.key, title, group, good: advanced, half: stalled, unknown: Math.max(0, objection.total - advanced - stalled - ended), bad: ended, of: objection.total };
    }
    return {
      id: objection.key,
      title,
      group,
      good: objection.resolved,
      half: 0,
      unknown: Math.max(0, objection.total - objection.open - objection.resolved),
      bad: objection.open,
      of: objection.total,
    };
  });
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
          return step ? <StepDetail step={step} type={type} /> : null;
        }}
      />
      <Table
        id="coach-improve-objections"
        title={p.coachTableObjections}
        column={byAfter ? p.coachColAdvanced : p.coachColResolved}
        rows={objectionRows}
        empty={p[noObjectionsKey(objections.length, listed.length)]}
        detail={(id) => {
          const objection = listed.find((candidate) => candidate.key === id);
          return objection ? <ObjectionDetail objection={objection} type={type} /> : null;
        }}
      />
    </div>
  );
}
