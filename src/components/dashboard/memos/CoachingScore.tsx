import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth";
import { coachingSurface, scoreBlocksLine } from "@/lib/coaching-score";
import { useMemoScore } from "@/features/coaching/hooks/useMemoScore";
import { usePostInteractionBrief } from "@/features/coaching/hooks/usePostInteractionBrief";
import { hasCoaching } from "@shared/ui/components/debrief.js";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { MemoMeetingChecklist } from "@/components/dashboard/memos/MemoMeetingChecklist";

export function CoachingScore({ memoId }: { memoId: string }) {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const p = t.product;
  const { user } = useAuth();
  const query = useMemoScore(memoId);
  // Same query as the debrief card next to it: when that card already says what went well and
  // what to change, this block keeps only the process state and the mark, never the same lines twice.
  const brief = usePostInteractionBrief(memoId);
  if (!query.data) return null;
  const surface = coachingSurface(query.data, p, user?.company?.role ?? "member");
  const lines = hasCoaching(brief.data)
    ? { strengths: [] as string[], improvements: [] as string[] }
    : { strengths: "strengths" in surface ? surface.strengths : [], improvements: "improvements" in surface ? surface.improvements : [] };
  const stepsInLine = (query.data.blocks?.steps?.applicable ?? 0) > 0;
  const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-3 p-5`;

  return (
    <section aria-labelledby="coaching-title" className={`${card} mb-6`}>
      <h2 id="coaching-title" className="text-[14px] font-medium tracking-tight text-foreground">{p.coachingProcessHeading}</h2>
      {surface.kind === "setup" ? (
        <div className="space-y-3">
          <p className="text-[13px] leading-relaxed text-muted-foreground">{surface.title}</p>
          {surface.action ? (
            <Button type="button" variant="outline" onClick={() => navigate("/dashboard/process")}>
              {surface.action}
            </Button>
          ) : (
            <p>{p.coachingAdminMustPublish}</p>
          )}
        </div>
      ) : null}
      {surface.kind === "waiting" || surface.kind === "internal" ? <p className="text-[13px] leading-relaxed text-muted-foreground">{surface.title}</p> : null}
      {surface.kind === "unscored" ? (
        <div className="space-y-2">
          <p className="text-[13px] leading-relaxed text-muted-foreground">{surface.title}</p>
          {lines.strengths.map((item) => <p key={item} className="text-[13.5px] text-foreground">{p.coachingStrength}: {item}</p>)}
          {lines.improvements.map((item) => <p key={item} className="text-[13.5px] text-foreground">{p.coachingImprovement}: {item}</p>)}
        </div>
      ) : null}
      {surface.kind === "scored" ? (
        <div className="space-y-2">
          {/* The mark and what it is made of, in one line: 7/10 · Pasos 4/5 · Cualificación 2/4. */}
          <p className="text-[13.5px] tabular-nums text-foreground">{scoreBlocksLine(query.data, p.pb2)}</p>
          {lines.strengths.map((item) => <p key={item} className="text-[13.5px] text-foreground">{p.coachingStrength}: {item}</p>)}
          {lines.improvements.map((item) => <p key={item} className="text-[13.5px] text-foreground">{p.coachingImprovement}: {item}</p>)}
          {surface.crmOutcome ? (
            <p className="text-[13px] leading-relaxed text-muted-foreground">{p.coachingCrmOutcome.replace("{outcome}", surface.crmOutcome)}</p>
          ) : null}
        </div>
      ) : null}
      {surface.kind === "scored" || surface.kind === "unscored" ? (
        <MemoMeetingChecklist memoId={memoId} showProgress={!stepsInLine} />
      ) : null}
    </section>
  );
}
