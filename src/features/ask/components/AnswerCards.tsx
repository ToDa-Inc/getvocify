import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, BookOpenText } from "@phosphor-icons/react";
import { useAuth } from "@/features/auth";
import { citedPlaybook, pointsChange, type AskCard, type AskCoachingCard, type AskTeamCard } from "@/lib/ask-cards";
import type { AskEvidence } from "@/lib/ask-thread";
import { HOS_PERIODS, processHealthView, type ProcessTone } from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { isManagerRole } from "@/lib/nav";
import { focusTitle, formatPercent, peerMedianLabel, trendArrow, trendOf, weekTotalLine } from "@/lib/rep-coaching";
import { objectionDisplayName, teamFlowFilterLabel } from "@/lib/team-insights";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const CARD = `ask-enter ${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} overflow-hidden shadow-[0_1px_2px_rgb(40_30_20/0.04),0_10px_24px_-18px_rgb(40_30_20/0.25)]`;

const TONE_DOT: Record<ProcessTone, string> = {
  process: "bg-warning",
  rep: "bg-beige",
  ok: "bg-success",
  neutral: "bg-muted-foreground/40",
};

/** One card's frame: what it is on the left, where it lives in the app on the right. */
function Frame({ label, to, place, children }: { label: string; to: string; place: string; children: ReactNode }) {
  return (
    <section className={CARD} aria-label={label}>
      <header className="flex items-center justify-between gap-3 border-b border-[hsl(var(--hairline))] bg-secondary/25 px-4 py-2">
        <p className="truncate text-[12.5px] text-muted-foreground">{label}</p>
        <Link
          to={to}
          className="inline-flex shrink-0 items-center gap-0.5 rounded-full text-[12.5px] text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {place}
          <ArrowUpRight size={12} weight="bold" aria-hidden="true" />
        </Link>
      </header>
      <div className="space-y-4 px-4 py-3.5">{children}</div>
    </section>
  );
}

/** A rate as a bar; the team's median, when known, as a tick on it. */
function RateBar({ rate, median, medianLabel }: { rate: number | null; median?: number | null; medianLabel?: string | null }) {
  return (
    <div className="relative h-1.5 rounded-full bg-muted-foreground/15">
      {rate !== null ? (
        <div className="h-full rounded-full bg-beige transition-[width] duration-500" style={{ width: `${Math.max(2, Math.round(rate * 100))}%` }} />
      ) : null}
      {median !== null && median !== undefined ? (
        <span
          title={medianLabel ?? undefined}
          className="absolute -top-[3px] h-3 w-px rounded-full bg-foreground/45"
          style={{ left: `${Math.round(median * 100)}%` }}
        />
      ) : null}
    </div>
  );
}

function CoachingCard({ card }: { card: AskCoachingCard }) {
  const { t } = useLanguage();
  const p = t.product;
  const focus = card.focus;
  return (
    <Frame label={p.navCoach} to="/dashboard/coach" place={p.navCoach}>
      {focus ? (
        <div className="space-y-2">
          <p className="text-[15px] leading-snug text-foreground">{focusTitle(p, focus)}</p>
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <RateBar rate={focus.week_total.applicable ? focus.week_total.done / focus.week_total.applicable : null} />
            </div>
            <span className="shrink-0 text-[12.5px] tabular-nums text-muted-foreground">{weekTotalLine(p, focus.week_total)}</span>
          </div>
          {focus.achieved ? <p className="text-[13px] text-success">{p.coachFocusAchieved}</p> : null}
          {focus.criterion ? (
            <p className="line-clamp-2 text-[13px] leading-relaxed text-muted-foreground">
              <span className="text-foreground/80">{p.coachFocusCriterion}:</span> {focus.criterion}
            </p>
          ) : null}
        </div>
      ) : null}
      {card.steps.length > 0 ? (
        <div className="space-y-2.5">
          <p className={THEME_TOKENS.typography.capsLabel}>{p.coachStepsHeading}</p>
          <ul className="space-y-2.5">
            {card.steps.map((step) => {
              const arrow = trendArrow(trendOf(step.rate, step.prev_rate));
              return (
                <li key={step.step_id || step.label} className="space-y-1">
                  <div className="flex items-baseline justify-between gap-3 text-[13px]">
                    <span className={`truncate ${focus?.label === step.label ? "text-foreground" : "text-foreground/80"}`}>{step.label}</span>
                    <span className="shrink-0 tabular-nums text-foreground">
                      {formatPercent(step.rate)}
                      {arrow ? <span className="ml-1 text-muted-foreground">{arrow}</span> : null}
                    </span>
                  </div>
                  <RateBar rate={step.rate} median={step.peer_median} medianLabel={peerMedianLabel(p, step.peer_median)} />
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </Frame>
  );
}

function TeamCard({ card }: { card: AskTeamCard }) {
  const { t } = useLanguage();
  const p = t.product;
  const period = HOS_PERIODS.find((option) => option.value === card.period);
  const change = pointsChange(card.adherence, card.previous);
  const label = [p.hosAdherence, period ? p[period.labelKey] : null].filter(Boolean).join(" · ");
  return (
    <Frame label={label} to="/dashboard/insights" place={p.navInsights}>
      {card.adherence !== null ? (
        <div className="flex items-baseline gap-2.5">
          <span className="text-[28px] leading-none tracking-tight tabular-nums text-foreground">{formatPercent(card.adherence)}</span>
          {change !== null && change !== 0 ? (
            <span
              className={`rounded-full px-1.5 py-0.5 text-[12px] tabular-nums ${change > 0 ? "bg-success/10 text-success" : "bg-warning/10 text-warning"}`}
            >
              {p.askPoints.replace("{value}", `${change > 0 ? "+" : "−"}${Math.abs(change)}`)}
            </span>
          ) : null}
          {change !== null ? <span className="text-[12.5px] text-muted-foreground">{p.hosVsPrevious}</span> : null}
        </div>
      ) : null}
      {card.process.length > 0 ? (
        <ul className="space-y-2">
          {card.process.map((flow) => {
            const view = processHealthView(flow, p);
            return (
              <li key={flow.motion} className="flex items-start gap-2.5">
                <span className={`mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full ${TONE_DOT[view.tone]}`} aria-hidden="true" />
                <div className="min-w-0">
                  <p className="text-[13.5px] leading-snug text-foreground">{view.title}</p>
                  <p className="text-[12.5px] text-muted-foreground">{teamFlowFilterLabel(flow.motion, p, p.motions)}</p>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
      {card.reps.length > 0 && !card.one_rep ? (
        <div className="space-y-1.5">
          <p className={THEME_TOKENS.typography.capsLabel}>{p.hosColFocus}</p>
          <ul className="-mx-2">
            {card.reps.map((rep) => {
              const row = (
                <>
                  <span className="truncate text-foreground">{rep.name}</span>
                  <span className="min-w-0 truncate text-right text-muted-foreground">
                    {rep.focus ? `${rep.focus.label}${rep.focus.rate !== null ? ` · ${formatPercent(rep.focus.rate)}` : ""}` : "—"}
                  </span>
                </>
              );
              const cls = "grid grid-cols-[auto_minmax(0,1fr)] items-center gap-4 rounded-lg px-2 py-1.5 text-[13px]";
              return (
                <li key={rep.user_id || rep.name}>
                  {rep.user_id ? (
                    <Link to={`/dashboard/insights/rep/${rep.user_id}`} className={`${cls} transition-colors hover:bg-secondary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring`}>
                      {row}
                    </Link>
                  ) : (
                    <div className={cls}>{row}</div>
                  )}
                </li>
              );
            })}
          </ul>
          {card.more_reps > 0 ? <p className="px-0 text-[12.5px] text-muted-foreground">{p.askMoreReps.replace("{count}", String(card.more_reps))}</p> : null}
        </div>
      ) : null}
    </Frame>
  );
}

/** The company's approved answers the reply cites, shown as the playbook wrote them. */
function PlaybookSources({ evidence }: { evidence: AskEvidence[] }) {
  const { t } = useLanguage();
  const p = t.product;
  const { user } = useAuth();
  const to = isManagerRole(user?.company?.role) ? "/dashboard/process#playbooks" : "/dashboard/playbook";
  return (
    <Frame label={p.askPlaybookSource} to={to} place={p.navPlaybook}>
      <ul className="space-y-3">
        {evidence.map((entry) => {
          const tags = [
            entry.category ? objectionDisplayName(entry.category, p.objections) : null,
            entry.rep ? teamFlowFilterLabel(entry.rep, p, p.motions) : null,
          ].filter(Boolean);
          return (
            <li key={entry.id} className="flex gap-3">
              <BookOpenText size={15} weight="light" className="mt-0.5 shrink-0 text-beige" aria-hidden="true" />
              <div className="min-w-0 space-y-1">
                {tags.length ? <p className="text-[12.5px] text-muted-foreground">{tags.join(" · ")}</p> : null}
                <p className="text-[14px] leading-relaxed text-foreground">“{entry.quote}”</p>
              </div>
            </li>
          );
        })}
      </ul>
    </Frame>
  );
}

export default function AnswerCards({ cards, evidence }: { cards: AskCard[]; evidence: AskEvidence[] }) {
  const playbook = citedPlaybook(evidence);
  if (cards.length === 0 && playbook.length === 0) return null;
  return (
    <div className="space-y-3">
      {cards.map((card) => (card.kind === "coaching" ? <CoachingCard key="coaching" card={card} /> : <TeamCard key="team" card={card} />))}
      {playbook.length > 0 ? <PlaybookSources evidence={playbook} /> : null}
    </div>
  );
}
