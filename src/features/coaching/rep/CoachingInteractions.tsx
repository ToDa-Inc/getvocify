import { useState } from "react";
import { Link } from "react-router-dom";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import {
  STEP_STATES,
  durationLabel,
  stateView,
  stepsDoneLine,
  type CoachInteraction,
  type InteractionFilters,
} from "@/lib/rep-coaching";
import { useCoachInteractions, useCoachSummary } from "./useRepCoaching";

const SELECT = "rounded-full border border-border bg-card px-4 py-1.5 text-sm text-foreground";

function Row({ item }: { item: CoachInteraction }) {
  const { t, language } = useLanguage();
  const p = t.product;
  const done = stepsDoneLine(p, item.steps);
  const duration = durationLabel(p, item.duration_s);
  const locale = language === "EN" ? "en-GB" : "es-ES";
  const date = item.observed_at
    ? new Date(item.observed_at).toLocaleDateString(locale, { day: "numeric", month: "short" })
    : "";
  // Plan §3.2: a missed step shows the moment it should have happened, when the engine has it.
  const missedWithQuote = item.steps.filter((step) => step.state === "missing" && step.quote);
  return (
    <li className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-4 space-y-2`} data-testid="coach-interaction-row">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>{date}</span>
        {duration ? <span>· {duration}</span> : null}
        {item.meeting_agreed ? <span className="rounded-full bg-success/10 px-2 py-0.5 text-success">{p.coachMeetingAgreed}</span> : null}
        <Link className="ml-auto text-foreground underline underline-offset-2" to={`/dashboard/memos/${item.memo_id}`}>
          {p.coachOpenMemo}
        </Link>
      </div>
      {item.summary_line ? <p className="text-sm text-foreground">{item.summary_line}</p> : null}
      <ul className="flex flex-wrap items-center gap-1.5 text-xs" aria-label={done ?? undefined}>
        {item.steps.map((step) => {
          const view = stateView(step.state);
          return (
            <li
              key={step.step_id}
              className="inline-flex items-center gap-1 rounded-full border border-border/70 px-2 py-0.5 text-foreground"
              title={String(p[view.labelKey])}
            >
              <span>{step.label}</span>
              <span aria-label={String(p[view.labelKey])}>{view.glyph}</span>
            </li>
          );
        })}
        {done ? <li className="pl-1 text-muted-foreground">{done}</li> : null}
      </ul>
      {missedWithQuote.map((step) => (
        <p key={step.step_id} className="text-xs text-muted-foreground">
          {step.label}: <span className="italic">“{step.quote}”</span>
        </p>
      ))}
    </li>
  );
}

export function CoachingInteractions() {
  const { t } = useLanguage();
  const p = t.product;
  const [filters, setFilters] = useState<InteractionFilters>({ stepId: "", state: "", meetingOnly: false });
  const summary = useCoachSummary();
  const query = useCoachInteractions(filters);
  const steps = summary.data?.steps ?? [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3" data-testid="coach-interaction-filters">
        <select aria-label={p.coachFilterStep} className={SELECT} value={filters.stepId} onChange={(e) => setFilters({ ...filters, stepId: e.target.value })}>
          <option value="">{p.coachFilterAllSteps}</option>
          {steps.map((step) => (
            <option key={step.step_id} value={step.step_id}>
              {step.label}
            </option>
          ))}
        </select>
        <select aria-label={p.coachFilterState} className={SELECT} value={filters.state} onChange={(e) => setFilters({ ...filters, state: e.target.value })}>
          <option value="">{p.coachFilterAllStates}</option>
          {STEP_STATES.map((state) => (
            <option key={state} value={state}>
              {String(p[stateView(state).labelKey])}
            </option>
          ))}
        </select>
        <button
          type="button"
          aria-pressed={filters.meetingOnly}
          onClick={() => setFilters({ ...filters, meetingOnly: !filters.meetingOnly })}
          className={`rounded-full border border-border px-3.5 py-1.5 text-sm ${filters.meetingOnly ? "bg-beige text-cream" : "bg-card text-muted-foreground"}`}
        >
          {p.coachFilterMeeting}
        </button>
      </div>
      {query.isError ? (
        <p className={THEME_TOKENS.typography.body}>{p.coachLoadFailed}</p>
      ) : !query.data ? (
        <p className={THEME_TOKENS.typography.body}>{p.coachLoading}</p>
      ) : query.data.items.length === 0 ? (
        <p className={THEME_TOKENS.typography.body}>{p.coachInteractionsEmpty}</p>
      ) : (
        <ul className="space-y-3">
          {query.data.items.map((item) => (
            <Row key={item.memo_id} item={item} />
          ))}
        </ul>
      )}
    </div>
  );
}
