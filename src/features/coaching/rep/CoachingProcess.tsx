import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { formatPercent, hasAnyPeer, objectionCountsLine, type CoachFlow } from "@/lib/rep-coaching";
import { objectionDisplayName } from "@/lib/team-insights";
import { CoachEmpty, CoachError, CoachLoading } from "./CoachingState";
import { useCoachProcess } from "./useRepCoaching";

// In the app's language, not the browser's.
function weekLabel(iso: string, language: string): string {
  const date = new Date(`${iso}T00:00:00`);
  const locale = language === "EN" ? "en-GB" : "es-ES";
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString(locale, { day: "numeric", month: "short" });
}

export function CoachingProcess({ flow }: { flow?: CoachFlow | null }) {
  const { t, language } = useLanguage();
  const p = t.product;
  const query = useCoachProcess(flow);
  const data = query.data;
  if (query.isError) return <CoachError onRetry={() => void query.refetch()} />;
  if (!data) return <CoachLoading />;
  if (data.steps.length === 0) return <CoachEmpty text={p.coachNoPlaybook} />;
  if (data.steps.every((step) => step.rate === null)) return <CoachEmpty text={p.coachProcessEmpty} />;
  const showPeer = hasAnyPeer(data.steps);
  const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5`;
  return (
    <div className="space-y-4">
      <section className={`${card} space-y-3`}>
        <p className={THEME_TOKENS.typography.capsLabel}>{p.coachProcessHelp}</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="coach-process-table">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-2 pr-4 font-normal">{p.coachProcessStep}</th>
                {data.weeks.map((week) => (
                  <th key={week} className="px-2 py-2 font-normal whitespace-nowrap">
                    {weekLabel(week, language)}
                  </th>
                ))}
                <th className="px-2 py-2 font-normal">{p.coachProcessOverall}</th>
                {showPeer ? <th className="px-2 py-2 font-normal">{p.coachProcessPeer}</th> : null}
              </tr>
            </thead>
            <tbody>
              {data.steps.map((step) => (
                <tr key={step.step_id} className="border-t border-border/60">
                  <td className="py-2 pr-4 text-foreground">{step.label}</td>
                  {data.weeks.map((week, index) => (
                    <td key={week} className="px-2 py-2 text-foreground whitespace-nowrap">
                      {formatPercent(step.by_week[index]?.rate)}
                    </td>
                  ))}
                  <td className="px-2 py-2 text-foreground whitespace-nowrap">{formatPercent(step.rate)}</td>
                  {showPeer ? <td className="px-2 py-2 text-muted-foreground whitespace-nowrap">{formatPercent(step.peer_median)}</td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className={`${card} space-y-2`}>
        <h2 className={THEME_TOKENS.typography.sectionTitle}>{p.coachObjectionsHeading}</h2>
        {data.objections.length === 0 ? (
          <p className={THEME_TOKENS.typography.body}>{p.coachObjectionsEmpty}</p>
        ) : (
          <ul className="space-y-1">
            {data.objections.map((o) => (
              <li key={o.category} className="flex justify-between gap-4 text-sm">
                <span className="text-foreground">{objectionDisplayName(o.category, p.objections)}</span>
                <span className="text-muted-foreground">{objectionCountsLine(p, o)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
