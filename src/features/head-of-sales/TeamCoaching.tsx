import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowRight, ArrowUp, ArrowUpRight, MessagesSquare, PhoneOff, Search, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Tile } from "@/features/coaching/rep/CoachKpis";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { VocifyLoader } from "@/components/ui/vocify-loader";
import type { HosPeriod, HosSalesRole } from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import { fill, formatPercent, trendOf } from "@/lib/rep-coaching";
import {
  causeLabel,
  cellValue,
  goalsMarked,
  hasRate,
  heatTone,
  lossesLine,
  MIN_GOALS,
  worksHasVerdict,
  type HeatTone,
  type TeamCoaching as TeamCoachingBody,
  type TeamEffect,
  type TeamLossCause,
  type TeamSide,
  type TeamStepCell,
  type TeamVerdict,
} from "@/lib/team-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { TeamFindings } from "./TeamFindings";
import { useTeamCoaching } from "./useTeamCoaching";

/** The same visual code as the reps' Coaching: colour only where it means something. */
const HEAT: Record<HeatTone, string> = {
  high: "bg-success/15 text-success",
  mid: "bg-warning/15 text-warning",
  low: "bg-destructive/10 text-destructive",
  few: "bg-secondary text-muted-foreground",
  none: "text-muted-foreground/50",
};
const VERDICT: Record<TeamVerdict, { dot: string; text: string; key: "teamVerdictHelps" | "teamVerdictHurts" | "teamVerdictNone" | "teamVerdictFew" }> = {
  helps: { dot: "bg-success", text: "text-success", key: "teamVerdictHelps" },
  hurts: { dot: "bg-destructive", text: "text-destructive", key: "teamVerdictHurts" },
  no_difference: { dot: "bg-muted-foreground/60", text: "text-foreground", key: "teamVerdictNone" },
  few_data: { dot: "bg-muted-foreground/30", text: "text-muted-foreground", key: "teamVerdictFew" },
};
// A comparison side needs this many calls before its share reads as a %, like team_coaching.MIN_GROUP.
const MIN_SIDE = 5;

function SectionHead({ id, title, meta }: { id: string; title: string; meta?: string }) {
  return (
    <div className="space-y-0.5">
      <h2 id={id} className={THEME_TOKENS.typography.sectionTitle}>{title}</h2>
      {meta ? <p className="text-[13px] text-muted-foreground">{meta}</p> : null}
    </div>
  );
}

function Cell({ cell, strong = false }: { cell: Pick<TeamStepCell, "done" | "applicable" | "rate">; strong?: boolean }) {
  return (
    <span
      className={cn(
        "block rounded-md px-2 py-1.5 text-center text-[13px] tabular-nums",
        strong ? "font-semibold" : "font-medium",
        HEAT[heatTone(cell)],
      )}
    >
      {cellValue(cell)}
    </span>
  );
}

/** A rep's or the team's whole "% del proceso": a % over three evaluated conversations or more, "—" under. */
function TotalCell({ evaluated, adherence }: { evaluated: number; adherence: number | null }) {
  const enough = hasRate(evaluated, adherence);
  return (
    <span
      className={cn(
        "block rounded-md px-2 py-1.5 text-center text-[13px] font-semibold tabular-nums",
        HEAT[enough ? heatTone({ applicable: evaluated, rate: adherence }) : "none"],
      )}
    >
      {enough ? formatPercent(adherence) : "—"}
    </span>
  );
}

/** 1. Do they follow the playbook: the team's %, then every rep against every step. */
function Follow({ data, period }: { data: TeamCoachingBody; period: HosPeriod }) {
  const { t } = useLanguage();
  const p = t.product;
  const { follow } = data;
  // The big number is the sum of the table under it, and is there only with enough behind it.
  const showRate = hasRate(follow.evaluated, follow.adherence);
  const showBefore = showRate && hasRate(follow.prev_evaluated, follow.prev_adherence);
  const trend = showBefore ? trendOf(follow.adherence, follow.prev_adherence) : null;
  const TrendIcon = trend === "up" ? ArrowUp : trend === "down" ? ArrowDown : ArrowRight;
  const teamCells: Record<string, TeamStepCell> = Object.fromEntries(follow.steps.map((step) => [step.step_id, step]));
  return (
    <section aria-labelledby="team-follow" className="space-y-5 px-3">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <SectionHead
          id="team-follow"
          title={p.teamFollowHeading}
          meta={fill(follow.reps.length === 1 ? p.teamFollowMetaOne : p.teamFollowMeta, { count: follow.conversations, reps: follow.reps.length })}
        />
        {showRate ? (
          <div className="text-right">
            <p className="text-3xl font-semibold leading-none tabular-nums text-foreground">{formatPercent(follow.adherence)}</p>
            {showBefore ? (
              <p className="mt-1.5 inline-flex items-center gap-1 text-xs text-muted-foreground">
                {fill(p.teamFollowBefore, { value: formatPercent(follow.prev_adherence) })}
                {trend ? (
                  <TrendIcon
                    aria-hidden
                    className={cn("h-3.5 w-3.5", trend === "up" ? "text-success" : trend === "down" ? "text-destructive" : "")}
                    strokeWidth={2}
                  />
                ) : null}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
      {follow.reps.length ? (
        // Many steps scroll inside the table, never the page.
        <div className="-mx-3 overflow-x-auto px-3">
          <table className="w-full border-separate border-spacing-1" data-testid="team-heatmap">
            <thead>
              <tr>
                <th scope="col" className="w-44 pb-1 text-left text-xs font-normal text-muted-foreground">{p.teamRepColumn}</th>
                {follow.steps.map((step) => (
                  <th key={step.step_id} scope="col" className="min-w-[5.5rem] pb-1 align-bottom text-xs font-normal text-muted-foreground">
                    <span title={step.label} className="line-clamp-2">{step.label}</span>
                    {step.outdated ? (
                      // The step was edited after these calls: why its column is short or empty.
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span tabIndex={0} className="mt-0.5 block cursor-default text-[11px] text-muted-foreground/70" data-testid="team-step-edited">
                            {p.teamStepEdited}
                          </span>
                        </TooltipTrigger>
                        <TooltipContent side="bottom">
                          {fill(step.outdated === 1 ? p.teamStepEditedHintOne : p.teamStepEditedHint, { count: step.outdated })}
                        </TooltipContent>
                      </Tooltip>
                    ) : null}
                  </th>
                ))}
                <th scope="col" className="min-w-[4.5rem] pb-1 align-bottom text-xs font-medium text-foreground">{p.teamTotalColumn}</th>
              </tr>
            </thead>
            <tbody>
              {follow.reps.map((rep) => (
                <tr key={rep.user_id}>
                  <th scope="row" className="pr-3 text-left font-normal">
                    <Link
                      to={`/dashboard/insights/rep/${rep.user_id}?period=${period}`}
                      className="block truncate text-sm text-foreground underline-offset-2 hover:underline"
                    >
                      {rep.name}
                    </Link>
                    <span className="text-xs tabular-nums text-muted-foreground">{rep.conversations}</span>
                  </th>
                  {follow.steps.map((step) => (
                    <td key={step.step_id}>
                      <Cell cell={rep.steps[step.step_id] ?? { done: 0, applicable: 0, rate: null }} />
                    </td>
                  ))}
                  <td>
                    <TotalCell evaluated={rep.evaluated} adherence={rep.adherence} />
                  </td>
                </tr>
              ))}
              {follow.reps.length > 1 ? (
                <tr>
                  <th scope="row" className="border-t border-border/60 pr-3 pt-2 text-left text-sm font-medium text-foreground">{p.teamTeamRow}</th>
                  {follow.steps.map((step) => (
                    <td key={step.step_id} className="border-t border-border/60 pt-2">
                      <Cell cell={teamCells[step.step_id]} strong />
                    </td>
                  ))}
                  <td className="border-t border-border/60 pt-2">
                    <TotalCell evaluated={follow.evaluated} adherence={follow.adherence} />
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function VerdictTag({ verdict }: { verdict: TeamVerdict }) {
  const { t } = useLanguage();
  const look = VERDICT[verdict];
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1.5 text-xs", look.text)}>
      <span aria-hidden className={cn("h-1.5 w-1.5 rounded-full", look.dot)} />
      {t.product[look.key]}
    </span>
  );
}

/** One side of a comparison: its share of meetings as a bar, "2/4" while the side is thin. */
function SideBar({ label, side, strong }: { label: string; side: TeamSide; strong: boolean }) {
  const enough = side.calls >= MIN_SIDE && side.rate !== null;
  return (
    <div className="grid grid-cols-[2.5rem_minmax(0,1fr)_3.5rem] items-center gap-3 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="h-1.5 overflow-hidden rounded-full bg-secondary">
        <span
          className={cn("block h-full rounded-full", strong ? "bg-foreground/60" : "bg-foreground/25")}
          style={{ width: `${enough ? Math.round((side.rate ?? 0) * 100) : 0}%` }}
        />
      </span>
      <span className="text-right tabular-nums text-foreground">
        {enough ? formatPercent(side.rate) : side.calls ? `${side.goals}/${side.calls}` : "—"}
      </span>
    </div>
  );
}

function EffectRow({ label, effect }: { label: string; effect: TeamEffect }) {
  const { t } = useLanguage();
  const p = t.product;
  return (
    <li className="space-y-2.5 py-4 first:pt-1">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-sm font-medium text-foreground">{label}</span>
        <VerdictTag verdict={effect.verdict} />
      </div>
      <SideBar label={p.teamWorksWith} side={effect.with} strong />
      <SideBar label={p.teamWorksWithout} side={effect.without} strong={false} />
    </li>
  );
}

/** 2. Does the playbook work: meetings with each step and without it. Nothing but one line until the
 * reps have marked enough meetings to compare. */
function Works({ data }: { data: TeamCoachingBody }) {
  const { t } = useLanguage();
  const p = t.product;
  const { works } = data;
  const steps = works.steps.filter((step) => step.with.calls + step.without.calls > 0);
  return (
    <section aria-labelledby="team-works" className="space-y-4">
      <SectionHead id="team-works" title={p.teamWorksHeading} meta={p.teamWorksMeta} />
      {worksHasVerdict(works) ? (
        <ul className="divide-y divide-border/60">
          {works.process ? <EffectRow label={p.teamWorksProcess} effect={works.process} /> : null}
          {steps.map((step) => (
            <EffectRow key={step.step_id} label={step.label} effect={step} />
          ))}
        </ul>
      ) : (
        <p className="text-[14.5px] leading-relaxed text-muted-foreground">
          {fill(p.teamWorksFewData, { goals: goalsMarked(works), min: MIN_GOALS })}
        </p>
      )}
    </section>
  );
}

function LossCause({ cause }: { cause: TeamLossCause }) {
  const { t, language } = useLanguage();
  const p = t.product;
  const example = cause.examples[0];
  const day = example ? new Date(example.observed_at).toLocaleDateString(language === "EN" ? "en-GB" : "es-ES", { day: "numeric", month: "short" }) : "";
  return (
    <li className="space-y-2 py-4 first:pt-1">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-sm font-medium text-foreground">{causeLabel(p, cause)}</span>
        <span className="shrink-0 text-sm tabular-nums text-foreground">
          {cause.count}
          <span className="text-muted-foreground"> · {formatPercent(cause.share)}</span>
        </span>
      </div>
      <span className="block h-1.5 overflow-hidden rounded-full bg-secondary">
        <span className="block h-full rounded-full bg-destructive/60" style={{ width: `${Math.round((cause.share ?? 0) * 100)}%` }} />
      </span>
      {example ? (
        <figure className="pt-1">
          <blockquote className="text-[13.5px] italic leading-relaxed text-foreground/80">«{example.quote}»</blockquote>
          <figcaption className="mt-0.5 text-xs text-muted-foreground">
            {example.rep} ·{" "}
            <Link to={`/dashboard/memos/${example.memo_id}`} className="inline-flex items-center gap-0.5 hover:text-foreground">
              {day}
              <ArrowUpRight aria-hidden className="h-3 w-3" />
            </Link>
            {example.from_history ? ` · ${p.teamFromHistory}` : ""}
          </figcaption>
        </figure>
      ) : null}
    </li>
  );
}

/** 3. Why we lose: the causes read from the lost calls themselves, most first. */
function Losses({ data }: { data: TeamCoachingBody }) {
  const { t } = useLanguage();
  const p = t.product;
  const { losses } = data;
  return (
    <section aria-labelledby="team-losses" className="space-y-4">
      <SectionHead id="team-losses" title={p.teamLossesHeading} meta={losses.total ? lossesLine(p, losses) : undefined} />
      {losses.total ? (
        <ul className="divide-y divide-border/60">
          {losses.causes.map((cause) => (
            <LossCause key={cause.cause} cause={cause} />
          ))}
        </ul>
      ) : (
        <p className="text-[14.5px] leading-relaxed text-muted-foreground">{p.teamLossesEmpty}</p>
      )}
    </section>
  );
}

// Why a call never became a conversation, from the most to the least: one neutral shade each, never red or green.
const REASON_SHADE = ["bg-foreground/60", "bg-foreground/40", "bg-foreground/25", "bg-foreground/15", "bg-foreground/10"];

/** The period's calls of the type as Coaching's KPI row, about how the team performs and not about a goal (a type may
 * have none): conversations of all the calls, the new objections, the opportunities let pass, and the calls that never
 * got to talk split by why, as one bar. */
function Activity({ data }: { data: TeamCoachingBody }) {
  const { t } = useLanguage();
  const p = t.product;
  const activity = data.activity!;
  const newObjections = data.findings?.new_objections ?? [];
  const opportunities = data.findings?.opportunities ?? [];
  const reasons = p.teamNotReached as Record<string, string>;
  const rest = activity.not_reached.filter((item) => item.count && reasons[item.reason]);
  const missed = rest.reduce((sum, item) => sum + item.count, 0);
  return (
    <div className="grid grid-cols-2 divide-border/50 border-y border-border/50 md:grid-cols-4 md:divide-x" data-testid="team-activity">
      <Tile
        icon={<MessagesSquare aria-hidden size={13} strokeWidth={1.5} />}
        label={p.coachKpiConversations}
        value={String(activity.conversations)}
        sub={fill(p.teamKpiOfCalls, { total: activity.calls })}
      />
      <Tile
        icon={<ShieldAlert aria-hidden size={13} strokeWidth={1.5} />}
        label={p.teamNewObjections}
        value={String(newObjections.length)}
        sub={newObjections.length ? fill(p.teamKpiTimes, { count: newObjections.reduce((sum, item) => sum + item.count, 0) }) : null}
      />
      <Tile
        icon={<Search aria-hidden size={13} strokeWidth={1.5} />}
        label={p.teamOpportunities}
        value={String(opportunities.length)}
        sub={opportunities.length ? fill(p.teamKpiTimes, { count: opportunities.reduce((sum, item) => sum + item.count, 0) }) : null}
      />
      <Tile
        icon={<PhoneOff aria-hidden size={13} strokeWidth={1.5} />}
        label={p.teamKpiNotReached}
        value={String(missed)}
        sub={
          missed ? (
            <span className="block space-y-1.5 pt-1">
              <span className="flex h-1.5 gap-px overflow-hidden rounded-full bg-secondary" role="img" aria-label={rest.map((item) => `${item.count} ${reasons[item.reason]}`).join(", ")}>
                {rest.map((item, index) => (
                  <span key={item.reason} className={REASON_SHADE[index] ?? REASON_SHADE[REASON_SHADE.length - 1]} style={{ flexGrow: item.count, flexBasis: 0 }} title={`${item.count} ${reasons[item.reason]}`} />
                ))}
              </span>
              <span className="flex flex-wrap gap-x-2.5 gap-y-0.5">
                {rest.map((item, index) => (
                  <span key={item.reason} className="inline-flex items-center gap-1 whitespace-nowrap">
                    <span aria-hidden className={cn("h-1.5 w-1.5 rounded-full", REASON_SHADE[index] ?? REASON_SHADE[REASON_SHADE.length - 1])} />
                    <span className="tabular-nums text-foreground/80">{item.count}</span> {reasons[item.reason]}
                  </span>
                ))}
              </span>
            </span>
          ) : null
        }
      />
    </div>
  );
}

/** Equipo: do they follow the playbook, does it work, why we lose. One interaction type at a time, on
 * one plane, with the reps' Coaching's visual code. */
export function TeamCoaching({ period, salesRole }: { period: HosPeriod; salesRole: HosSalesRole }) {
  const { t } = useLanguage();
  const p = t.product;
  const [type, setType] = useState<string | null>(null);
  const query = useTeamCoaching(period, salesRole, type);
  if (query.isError) {
    return (
      <div className="flex flex-wrap items-center gap-3 px-3" role="alert">
        <p className={THEME_TOKENS.typography.body}>{p.teamReadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void query.refetch()}>
          {p.coachRetry}
        </Button>
      </div>
    );
  }
  if (!query.data) {
    return (
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" label={p.teamLoading} />
      </div>
    );
  }
  const data = query.data;
  if (!data.type) return <p className={`px-3 ${THEME_TOKENS.typography.body}`}>{p.teamNoType}</p>;
  const name = (key: string, label: string | null) => label || p.pb2.typeLabels[key as keyof typeof p.pb2.typeLabels] || motionLabel(key, p.motions);
  return (
    <div className={cn("space-y-14 transition-opacity", query.isPlaceholderData && "opacity-60")} aria-busy={query.isPlaceholderData} data-testid="team-coaching">
      {data.types.length > 1 ? (
        <div className="px-3">
          <Segmented
            value={data.type}
            onValueChange={setType}
            options={data.types.map((option) => ({ value: option.key, label: name(option.key, option.label) }))}
            aria-label={p.coachTypeLabel}
          />
        </div>
      ) : null}
      {data.activity?.calls ? <div className="px-3"><Activity data={data} /></div> : null}
      <TeamFindings data={data} />
      <Follow data={data} period={period} />
      {worksHasVerdict(data.works) || data.losses.total ? (
        <div className="grid gap-12 px-3 lg:grid-cols-2 lg:gap-14">
          {worksHasVerdict(data.works) ? <Works data={data} /> : null}
          {data.losses.total ? <Losses data={data} /> : null}
        </div>
      ) : null}
    </div>
  );
}
