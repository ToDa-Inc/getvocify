import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { useCoachExamples } from "./useRepCoaching";
import { objectionDisplayName } from "@/lib/team-insights";

export function CoachingExamples() {
  const { t } = useLanguage();
  const p = t.product;
  const query = useCoachExamples();
  const data = query.data;
  if (query.isError) return <p className={THEME_TOKENS.typography.body}>{p.coachLoadFailed}</p>;
  if (!data) return <p className={THEME_TOKENS.typography.body}>{p.coachLoading}</p>;
  if (data.steps.length === 0 && data.objections.length === 0) {
    return <p className={THEME_TOKENS.typography.body}>{p.coachExamplesEmpty}</p>;
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
          <h3 className="text-foreground">{objectionDisplayName(o.category, p.objections)}</h3>
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
