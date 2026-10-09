import { Link } from "react-router-dom";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { PROCESS_HREF, processHealthView, type ProcessHealthFlow, type ProcessTone } from "@/lib/head-of-sales";
import { teamFlowFilterLabel } from "@/lib/team-insights";

const TONE_DOT: Record<ProcessTone, string> = {
  process: "bg-warning",
  rep: "bg-beige",
  ok: "bg-success",
  neutral: "bg-muted-foreground/40",
};

/** Plan §0/§5: tells a rep problem (coaching) from a playbook problem (fix the process). */
export function ProcessHealth({ flows }: { flows: ProcessHealthFlow[] }) {
  const { t } = useLanguage();
  const p = t.product;
  if (!flows.length) return null;
  // Flows with a verdict first; a flow whose goal can't be read per interaction goes last.
  const ordered = [...flows].sort(
    (a, b) => Number(a.verdict === "goal_not_measurable") - Number(b.verdict === "goal_not_measurable"),
  );
  return (
    <section
      aria-labelledby="hos-process"
      className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-4`}
      data-testid="hos-process-health"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id="hos-process" className={THEME_TOKENS.typography.sectionTitle}>{p.hosProcessHeading}</h2>
          <p className="text-xs text-muted-foreground mt-1">{p.hosProcessSubtitle}</p>
        </div>
        <Link to={PROCESS_HREF} className="shrink-0 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground">
          {p.hosProcessReview}
        </Link>
      </div>
      <ul className="space-y-4">
        {ordered.map((flow) => {
          const view = processHealthView(flow, p);
          return (
            <li key={flow.motion} className="border-t border-border/50 pt-4 first:border-0 first:pt-0" data-testid="hos-process-flow">
              <p className="text-xs text-muted-foreground">
                {teamFlowFilterLabel(flow.motion, p, p.motions)} · {p.hosProcessScored.replace("{count}", String(flow.scored))}
              </p>
              <p className="mt-1 flex items-center gap-2 text-[15px] text-foreground">
                <span className={`h-2 w-2 rounded-full ${TONE_DOT[view.tone]}`} aria-hidden />
                {view.title}
              </p>
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{view.detail}</p>
              {flow.matrix ? (
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">{p.hosProcessBreakdown}</summary>
                  <table className="mt-2 text-sm">
                    <thead>
                      <tr>
                        <th scope="col" className="pr-6" />
                        <th scope="col" className="pr-6 text-left text-xs font-normal text-muted-foreground">{p.hosProcessGoal}</th>
                        <th scope="col" className="text-left text-xs font-normal text-muted-foreground">{p.hosProcessNoGoal}</th>
                      </tr>
                    </thead>
                    <tbody className="tabular-nums">
                      <tr>
                        <th scope="row" className="pr-6 text-left font-normal text-muted-foreground">{p.hosProcessFollows}</th>
                        <td className="pr-6">{flow.matrix.follows_goal}</td>
                        <td>{flow.matrix.follows_no_goal}</td>
                      </tr>
                      <tr>
                        <th scope="row" className="pr-6 text-left font-normal text-muted-foreground">{p.hosProcessDeviates}</th>
                        <td className="pr-6">{flow.matrix.deviates_goal}</td>
                        <td>{flow.matrix.deviates_no_goal}</td>
                      </tr>
                    </tbody>
                  </table>
                </details>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
