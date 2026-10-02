import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { CoachEmpty, CoachError, CoachLoading } from "./CoachingState";
import { useCoachExamples } from "./useRepCoaching";
import { objectionDisplayName } from "@/lib/team-insights";
import type { CoachFlow } from "@/lib/rep-coaching";

export function CoachingExamples({ flow }: { flow?: CoachFlow | null }) {
  const { t } = useLanguage();
  const p = t.product;
  const query = useCoachExamples(flow);
  const data = query.data;
  if (query.isError) return <CoachError onRetry={() => void query.refetch()} />;
  if (!data) return <CoachLoading />;
  if (data.steps.length === 0 && data.objections.length === 0) {
    return <CoachEmpty text={p.coachExamplesEmptyWhy} />;
  }
  const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5`;
  return (
    <div className="space-y-4" data-testid="coach-examples">
      <h2 className={THEME_TOKENS.typography.sectionTitle}>{p.coachExamplesStepsHeading}</h2>
      {data.steps.map((step) => (
        <section key={step.step_id} className={`${card} space-y-2`}>
          <h3 className="text-foreground">{step.label}</h3>
          <p className="text-sm text-muted-foreground">{step.criterion}</p>
          {step.example ? <p className="text-sm italic text-foreground">“{step.example}”</p> : null}
          {step.moments.length > 0 ? (
            <div className="space-y-1 pt-1">
              <p className={THEME_TOKENS.typography.capsLabel}>{p.coachExamplesQuotesHeading}</p>
              {step.moments.slice(0, 3).map((moment, index) => (
                <blockquote key={index} className="border-l-2 border-beige/40 pl-3 text-sm text-foreground">
                  “{moment.quote}”
                </blockquote>
              ))}
            </div>
          ) : null}
        </section>
      ))}
      {data.objections.length > 0 ? <h2 className={THEME_TOKENS.typography.sectionTitle}>{p.coachExamplesObjectionsHeading}</h2> : null}
      {data.objections.map((o) => (
        <section key={o.category} className={`${card} space-y-2`}>
          <h3 className="text-foreground">{o.label || objectionDisplayName(o.category, p.objections)}</h3>
          {o.guidance ? (
            <div>
              <p className={THEME_TOKENS.typography.capsLabel}>{p.coachExamplesGuidance}</p>
              <p className="text-sm text-foreground">{o.guidance}</p>
            </div>
          ) : null}
          {o.best_response ? (
            <div>
              <p className={THEME_TOKENS.typography.capsLabel}>{p.coachExamplesBestResponse}</p>
              <p className="text-sm italic text-foreground">“{o.best_response}”</p>
            </div>
          ) : null}
        </section>
      ))}
    </div>
  );
}
