import { useState } from "react";
import { Link } from "react-router-dom";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { Toggle } from "@/components/ui/toggle";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  STEP_STATES,
  type CoachFlow,
  durationLabel,
  stateView,
  stepsDoneLine,
  type CoachInteraction,
  type InteractionFilters,
} from "@/lib/rep-coaching";
import { CoachEmpty, CoachError, CoachLoading } from "./CoachingState";
import { useCoachInteractions, useCoachSummary } from "./useRepCoaching";

/** Sentinels for empty filter states (showing all items). */
const FILTER_NONE_STEP = "__none_step__";
const FILTER_NONE_STATE = "__none_state__";

function Row({ item }: { item: CoachInteraction }) {
  const { t, language } = useLanguage();
  const p = t.product;
  const done = stepsDoneLine(p, item.steps);
  const duration = durationLabel(p, item.duration_s);
  const locale = language === "EN" ? "en-GB" : "es-ES";
  const date = item.observed_at
    ? new Date(item.observed_at).toLocaleDateString(locale, { day: "numeric", month: "short" })
    : "";
  // Plan §3.2: a missed step says what to do next time (v8 advice) and, as context, the moment it
  // should have happened, when the engine has either.
  const missed = item.steps.filter(
    (step) => (step.state === "missing" && (step.advice || step.quote)) || (step.state === "improvable" && step.advice),
  );
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
      {missed.map((step) => (
        <div key={step.step_id} className="space-y-0.5 text-xs" data-testid="coach-missed-step">
          <p className="text-foreground">
            <span className="font-medium">
              {step.label}
              {step.state === "improvable" ? ` (${String(p.coachStateImprovable).toLowerCase()})` : ""}:
            </span>{" "}
            {step.advice ? step.advice : <span className="italic text-muted-foreground">“{step.quote}”</span>}
          </p>
          {step.advice && step.quote ? (
            <p className="italic text-muted-foreground">“{step.quote}”</p>
          ) : null}
        </div>
      ))}
    </li>
  );
}

export function CoachingInteractions({ flow }: { flow?: CoachFlow | null }) {
  const { t } = useLanguage();
  const p = t.product;
  const [filters, setFilters] = useState<InteractionFilters>({ stepId: "", state: "", meetingOnly: false });
  const summary = useCoachSummary(flow);
  const query = useCoachInteractions(filters, flow);
  const filtered = Boolean(filters.stepId || filters.state || filters.meetingOnly);
  const steps = summary.data?.steps ?? [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3" data-testid="coach-interaction-filters">
        <Select
          value={filters.stepId || FILTER_NONE_STEP}
          onValueChange={(v) => setFilters({ ...filters, stepId: v === FILTER_NONE_STEP ? "" : v })}
        >
          <SelectTrigger aria-label={p.coachFilterStep} variant="chip">
            <SelectValue placeholder={p.coachFilterAllSteps} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={FILTER_NONE_STEP}>{p.coachFilterAllSteps}</SelectItem>
            {steps.map((step) => (
              <SelectItem key={step.step_id} value={step.step_id}>
                {step.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={filters.state || FILTER_NONE_STATE}
          onValueChange={(v) => setFilters({ ...filters, state: v === FILTER_NONE_STATE ? "" : v })}
        >
          <SelectTrigger aria-label={p.coachFilterState} variant="chip">
            <SelectValue placeholder={p.coachFilterAllStates} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={FILTER_NONE_STATE}>{p.coachFilterAllStates}</SelectItem>
            {STEP_STATES.map((state) => (
              <SelectItem key={state} value={state}>
                {String(p[stateView(state).labelKey])}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Toggle
          variant="chip"
          size="sm"
          pressed={filters.meetingOnly}
          onPressedChange={() => setFilters({ ...filters, meetingOnly: !filters.meetingOnly })}
          aria-label={p.coachFilterMeeting}
        >
          {p.coachFilterMeeting}
        </Toggle>
      </div>
      {query.isError ? (
        <CoachError onRetry={() => void query.refetch()} />
      ) : !query.data ? (
        <CoachLoading />
      ) : query.data.items.length === 0 ? (
        <CoachEmpty text={filtered ? p.coachInteractionsEmpty : (flow ?? summary.data?.flow) === "ae" ? p.coachMeetingsEmpty : p.coachCallsEmpty} />
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
