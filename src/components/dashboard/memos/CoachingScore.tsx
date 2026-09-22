import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth";
import { coachingSurface } from "@/lib/coaching-score";
import { useMemoScore } from "@/features/coaching/hooks/useMemoScore";
import { useLanguage } from "@/lib/i18n";

export function CoachingScore({ memoId }: { memoId: string }) {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const p = t.product;
  const { user } = useAuth();
  const query = useMemoScore(memoId);
  if (!query.data) return null;
  const surface = coachingSurface(query.data, user?.company?.role ?? "member");

  return (
    <section aria-labelledby="coaching-title" className="mb-6 space-y-3">
      <h2 id="coaching-title" className="text-lg">{p.coachingProcessHeading}</h2>
      {surface.kind === "setup" ? (
        <div>
          <p>{surface.title}</p>
          {surface.action ? (
            <Button type="button" variant="outline" onClick={() => navigate("/dashboard/settings/playbooks")}>
              {surface.action}
            </Button>
          ) : (
            <p>{p.coachingAdminMustPublish}</p>
          )}
        </div>
      ) : null}
      {surface.kind === "waiting" ? <p>{surface.title}</p> : null}
      {surface.kind === "unscored" ? (
        <div>
          <p>{surface.title}</p>
          {surface.strengths.map((item) => <p key={item}>{p.coachingStrength}: {item}</p>)}
          {surface.improvements.map((item) => <p key={item}>{p.coachingImprovement}: {item}</p>)}
        </div>
      ) : null}
      {surface.kind === "scored" ? (
        <div>
          {surface.strengths.map((item) => <p key={item}>{p.coachingStrength}: {item}</p>)}
          {surface.improvements.map((item) => <p key={item}>{p.coachingImprovement}: {item}</p>)}
          {surface.crmOutcome ? (
            <p>{p.coachingCrmOutcome.replace("{outcome}", surface.crmOutcome)}</p>
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
