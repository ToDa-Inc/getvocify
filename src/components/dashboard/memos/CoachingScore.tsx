import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth";
import { coachingSurface } from "@/lib/coaching-score";
import { useMemoScore } from "@/features/coaching/hooks/useMemoScore";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

export function CoachingScore({ memoId }: { memoId: string }) {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const p = t.product;
  const { user } = useAuth();
  const query = useMemoScore(memoId);
  if (!query.data) return null;
  const surface = coachingSurface(query.data, p, user?.company?.role ?? "member");

  const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-3 p-5`;

  return (
    <section aria-labelledby="coaching-title" className={`${card} mb-6`}>
      <h2 id="coaching-title" className={THEME_TOKENS.typography.sectionTitle}>{p.coachingProcessHeading}</h2>
      {surface.kind === "setup" ? (
        <div className="space-y-3">
          <p className={THEME_TOKENS.typography.body}>{surface.title}</p>
          {surface.action ? (
            <Button type="button" variant="outline" onClick={() => navigate("/dashboard/settings/playbooks")}>
              {surface.action}
            </Button>
          ) : (
            <p>{p.coachingAdminMustPublish}</p>
          )}
        </div>
      ) : null}
      {surface.kind === "waiting" ? <p className={THEME_TOKENS.typography.body}>{surface.title}</p> : null}
      {surface.kind === "unscored" ? (
        <div className="space-y-2">
          <p className={THEME_TOKENS.typography.body}>{surface.title}</p>
          {surface.strengths.map((item) => <p key={item} className="text-[15px] text-foreground">{p.coachingStrength}: {item}</p>)}
          {surface.improvements.map((item) => <p key={item} className="text-[15px] text-foreground">{p.coachingImprovement}: {item}</p>)}
        </div>
      ) : null}
      {surface.kind === "scored" ? (
        <div className="space-y-2">
          {surface.strengths.map((item) => <p key={item} className="text-[15px] text-foreground">{p.coachingStrength}: {item}</p>)}
          {surface.improvements.map((item) => <p key={item} className="text-[15px] text-foreground">{p.coachingImprovement}: {item}</p>)}
          {surface.crmOutcome ? (
            <p className={THEME_TOKENS.typography.body}>{p.coachingCrmOutcome.replace("{outcome}", surface.crmOutcome)}</p>
          ) : null}
          <details>
            <summary>{p.coachingViewCriteria}</summary>
            <p>{surface.value}</p>
            {surface.adherence !== null ? <p>{surface.adherence}</p> : null}
          </details>
        </div>
      ) : null}
    </section>
  );
}
