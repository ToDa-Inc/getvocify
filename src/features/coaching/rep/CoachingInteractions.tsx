import { useState } from "react";
import { Link } from "react-router-dom";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { Toggle } from "@/components/ui/toggle";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChevronDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  STEP_STATES,
  type CoachFlow,
  cleanSummaryLine,
  countTone,
  durationLabel,
  stateView,
  stepsDone,
  type CoachInteraction,
  type InteractionFilters,
} from "@/lib/rep-coaching";
import { CoachEmpty, CoachError, CoachLoading } from "./CoachingState";
import { useCoachInteractions, useCoachSummary } from "./useRepCoaching";

/** Sentinels for empty filter states (showing all items). */
const FILTER_NONE_STEP = "__none_step__";
const FILTER_NONE_STATE = "__none_state__";

const TONE_TEXT = { success: "text-success", warning: "text-warning", destructive: "text-destructive", muted: "text-foreground" } as const;

function Tile({ label, value, tone }: { label: string; value: string; tone: keyof typeof TONE_TEXT }) {
  return (
    <div className={`${THEME_TOKENS.radius.control} bg-secondary/40 px-3.5 py-3`}>
      <p className={THEME_TOKENS.typography.fieldLabel}>{label}</p>
      <p className={`mt-1 text-[1.6rem] leading-none tracking-tight tabular-nums ${TONE_TEXT[tone]}`}>{value}</p>
    </div>
  );
}

function dateLine(iso: string | null, language: string): string {
  if (!iso) return "";
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  const locale = language === "EN" ? "en-GB" : "es-ES";
  return `${at.toLocaleDateString(locale, { weekday: "short", day: "numeric", month: "short" })} · ${at.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })}`;
}

/** One call: when, how it ended, steps done and the meeting, and what slipped. The card opens the call. */
function CallCard({ item }: { item: CoachInteraction }) {
  const { t, language } = useLanguage();
  const p = t.product;
  const { done, total } = stepsDone(item.steps);
  const duration = durationLabel(p, item.duration_s);
  const slipped = item.steps.filter((step) => step.state === "missing").map((step) => step.label);
  return (
    <li>
      <Link
        to={`/dashboard/memos/${item.memo_id}`}
        className={`block space-y-3 ${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} ${THEME_TOKENS.cards.hover} p-5`}
        data-testid="coach-interaction-row"
      >
        <div className="space-y-1">
          <p className={THEME_TOKENS.typography.capsLabel}>
            {dateLine(item.observed_at, language)}
            {duration ? ` · ${duration}` : ""}
          </p>
          <p className="line-clamp-2 text-[15px] leading-snug text-foreground">{cleanSummaryLine(item.summary_line)}</p>
        </div>
        <div className="grid max-w-sm grid-cols-2 gap-2">
          <Tile label={p.coachCardSteps} value={total ? `${done}/${total}` : "—"} tone={countTone(done, total)} />
          {/* Only a "yes" is shown, as before: meeting_agreed comes from the rep's own outcome or the
              CRM stage, and a missing declaration is not a "no". */}
          {item.meeting_agreed ? <Tile label={p.coachCardMeeting} value={p.coachCardYes} tone="success" /> : null}
        </div>
        {slipped.length ? (
          <p className="text-[13px] text-muted-foreground" data-testid="coach-missed-step">
            <span className="text-destructive">{p.coachCardSlipped}</span> {slipped.join(" · ")}
          </p>
        ) : null}
      </Link>
    </li>
  );
}

/** Voicemail and no answer: activity, not evaluated, so one quiet line each under a fold. */
function NoConversation({ items }: { items: CoachInteraction[] }) {
  const { t, language } = useLanguage();
  if (!items.length) return null;
  return (
    <Collapsible>
      <CollapsibleTrigger className={`group flex w-full items-center gap-1.5 border-t border-border/60 px-0.5 pt-3.5 ${THEME_TOKENS.typography.capsLabel} transition-colors hover:text-foreground`}>
        {t.product.coachNoConversation} · <span className="tabular-nums">{items.length}</span>
        <ChevronDown size={14} strokeWidth={1.5} className="ml-auto transition-transform group-data-[state=open]:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-2">
          {items.map((item) => (
            <li key={item.memo_id} className="grid grid-cols-[9rem_minmax(0,1fr)] items-baseline gap-3 border-t border-border/60 px-0.5 py-2 first:border-t-0">
              <span className={`tabular-nums ${THEME_TOKENS.typography.capsLabel}`}>{dateLine(item.observed_at, language)}</span>
              <Link to={`/dashboard/memos/${item.memo_id}`} className="truncate text-sm text-foreground hover:underline">
                {cleanSummaryLine(item.summary_line)}
              </Link>
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
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
        <div className="space-y-4">
          <ul className="space-y-3">
            {query.data.items
              .filter((item) => item.is_conversation)
              .map((item) => (
                <CallCard key={item.memo_id} item={item} />
              ))}
          </ul>
          <NoConversation items={query.data.items.filter((item) => !item.is_conversation)} />
        </div>
      )}
    </div>
  );
}
