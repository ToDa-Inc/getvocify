import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import {
  conversionSentence,
  focusTitle,
  focusWhy,
  formatPercent,
  numberVsLast,
  peerMedianLabel,
  trendArrow,
  trendOf,
  weekTotalLine,
  type CoachFocus,
  type CoachNumbers,
  type CoachStepRate,
} from "@/lib/rep-coaching";
import { useCoachSummary } from "./useRepCoaching";

const CARD = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5`;
// Weekday initial in the app's language, not the browser's (a Spanish UI says L M X J V).
function dayInitial(iso: string, language: string): string {
  const date = new Date(`${iso}T00:00:00`);
  const locale = language === "EN" ? "en-GB" : "es-ES";
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(locale, { weekday: "narrow" });
}

function FocusCard({ focus }: { focus: CoachFocus }) {
  const { t, language } = useLanguage();
  const p = t.product;
  return (
    <section className={`${CARD} space-y-4`} data-testid="coach-focus">
      <div className="space-y-1">
        <h2 className="text-lg text-foreground">{focusTitle(p, focus)}</h2>
        <p className={THEME_TOKENS.typography.body}>{focusWhy(p, focus.why)}</p>
      </div>
      <div>
        <p className={THEME_TOKENS.typography.capsLabel}>{p.coachFocusProgress}</p>
        <div className="mt-2 flex items-center gap-2">
          {focus.progress.map((day) => {
            const tone = day.applicable === 0 ? "bg-muted-foreground/20" : day.done === day.applicable ? "bg-success" : day.done > 0 ? "bg-warning" : "bg-muted-foreground/40";
            return (
              <div key={day.date} className="flex flex-col items-center gap-1" title={`${day.done}/${day.applicable}`}>
                <span className={`h-3 w-8 rounded-full ${tone}`} />
                <span className="text-[11px] text-muted-foreground">{dayInitial(day.date, language)}</span>
              </div>
            );
          })}
          <span className="ml-2 text-sm text-foreground">{weekTotalLine(p, focus.week_total)}</span>
        </div>
        {focus.achieved ? <p className="mt-2 text-sm text-success">{p.coachFocusAchieved}</p> : null}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <p className={THEME_TOKENS.typography.capsLabel}>{p.coachFocusCriterion}</p>
          <p className="text-sm text-foreground">{focus.criterion}</p>
        </div>
        {focus.example ? (
          <div>
            <p className={THEME_TOKENS.typography.capsLabel}>{p.coachFocusExample}</p>
            <p className="text-sm italic text-foreground">“{focus.example}”</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function StepStrip({ steps, onOpenProcess }: { steps: CoachStepRate[]; onOpenProcess: () => void }) {
  const { t } = useLanguage();
  const p = t.product;
  return (
    <section className={`${CARD} space-y-3`} data-testid="coach-step-strip">
      <h2 className={THEME_TOKENS.typography.sectionTitle}>{p.coachStepsHeading}</h2>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {steps.map((step) => {
          const arrow = trendArrow(trendOf(step.rate, step.prev_rate));
          const peer = peerMedianLabel(p, step.peer_median);
          return (
            <button
              key={step.step_id}
              type="button"
              onClick={onOpenProcess}
              className="rounded-lg border border-border/70 p-3 text-left transition-colors hover:border-beige/25"
            >
              <p className="text-sm text-foreground">{step.label}</p>
              <p className="mt-1 text-lg text-foreground">
                {formatPercent(step.rate)} {arrow ? <span className="text-muted-foreground">{arrow}</span> : null}
              </p>
              {step.rate !== null ? (
                <div className="relative mt-1 h-1 rounded-full bg-muted-foreground/15">
                  <div className="h-1 rounded-full bg-beige" style={{ width: `${Math.round(step.rate * 100)}%` }} />
                  {step.peer_median !== null ? (
                    <div className="absolute top-[-2px] h-2 w-px bg-muted-foreground" style={{ left: `${Math.round(step.peer_median * 100)}%` }} />
                  ) : null}
                </div>
              ) : null}
              {peer ? <p className="mt-1 text-xs text-muted-foreground">{peer}</p> : null}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function Numbers({ current, previous }: { current: CoachNumbers; previous: CoachNumbers }) {
  const { t } = useLanguage();
  const p = t.product;
  const tiles = [
    { label: p.coachNumConversations, now: current.conversations, prev: previous.conversations },
    { label: p.coachNumMeetings, now: current.meetings_agreed, prev: previous.meetings_agreed },
    { label: p.coachNumProcess, now: current.process_complete, prev: previous.process_complete },
  ];
  return (
    <section className={`${CARD} space-y-3`} data-testid="coach-numbers">
      <h2 className={THEME_TOKENS.typography.sectionTitle}>{p.coachNumbersHeading}</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        {tiles.map((tile) => (
          <div key={tile.label}>
            <p className={THEME_TOKENS.typography.capsLabel}>{tile.label}</p>
            <p className="text-2xl text-foreground">{tile.now}</p>
            <p className="text-xs text-muted-foreground">{numberVsLast(p, tile.prev)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export function CoachingSummary({ onOpenProcess }: { onOpenProcess: () => void }) {
  const { t } = useLanguage();
  const p = t.product;
  const query = useCoachSummary();
  const data = query.data;
  if (query.isError) return <p className={THEME_TOKENS.typography.body}>{p.coachLoadFailed}</p>;
  if (!data) return <p className={THEME_TOKENS.typography.body}>{p.coachLoading}</p>;
  if (!data.playbook_published) return <p className={THEME_TOKENS.typography.body}>{p.coachNoPlaybook}</p>;
  const conversion = conversionSentence(p, data.conversion);
  const hasData = data.numbers.interactions > 0 || data.prev_numbers.interactions > 0;
  return (
    <div className="space-y-4">
      {data.focus ? (
        <FocusCard focus={data.focus} />
      ) : (
        <section className={CARD} data-testid="coach-focus">
          <p className="text-foreground">{hasData ? p.coachFocusNone : p.coachNoData}</p>
        </section>
      )}
      <StepStrip steps={data.steps} onOpenProcess={onOpenProcess} />
      <Numbers current={data.numbers} previous={data.prev_numbers} />
      {conversion ? (
        <p className={`${CARD} text-foreground`} data-testid="coach-conversion">
          {conversion}
        </p>
      ) : null}
    </div>
  );
}
