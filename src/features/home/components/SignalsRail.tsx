import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useTeamAdherence } from "@/features/head-of-sales/useTeamAdherence";
import { flowShortName, summaryDiagnosis, type Diagnosis } from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import type { ProductTranslations } from "@/lib/product-catalog";
import type { TrendPayload } from "@/lib/team-adherence-trend";
import { teamFlowFilterLabel } from "@/lib/team-insights";
import { signalReps, teamSignals, type SignalTextKey, type TeamSignal } from "@/lib/team-signals";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { api } from "@/shared/lib/api-client";

const TEAM = "/dashboard/insights";
const INVITE = "/dashboard/settings/team";
const FIVE_MINUTES = 5 * 60 * 1000;

/** The long diagnosis line behind a short signal: its evidence, on hover. */
const DIAGNOSIS_OF: Partial<Record<SignalTextKey, Diagnosis["key"]>> = {
  signalPlaybook: "hosDiagPlaybook",
  signalPlaybookNoEffect: "hosDiagPlaybookNoEffect",
  signalCoach: "hosDiagCoach",
};

function fill(template: string, params: Record<string, string | number>) {
  return Object.entries(params).reduce((text, [key, value]) => text.split(`{${key}}`).join(String(value)), template);
}

/** The words for one signal: the line, the question it asks, and what it rests on. */
function signalCopy(signal: TeamSignal, p: ProductTranslations) {
  const params = { ...signal.params };
  if (typeof params.flow === "string") params.flow = flowShortName(params.flow, teamFlowFilterLabel(params.flow, p, p.motions));
  const diagnosis = DIAGNOSIS_OF[signal.textKey];
  const evidence = diagnosis ? p[diagnosis] : signal.textKey === "signalDrop" ? p.home.signalDropEvidence : null;
  return {
    text: fill(p.home[signal.textKey], params),
    question: fill(p.home[signal.question], params),
    evidence: evidence ? fill(evidence, params) : null,
  };
}

/**
 * The Head of Sales' side of Inicio: at most three things about the team worth a question, by rule
 * (last 30 days, and the last four weeks of adherence against the four before). A click puts the
 * question in the composer to edit or send; nothing is sent on its own.
 */
export function SignalsRail({ onAsk }: { onAsk: (question: string) => void }) {
  const { t } = useLanguage();
  const p = t.product;
  const team = useTeamAdherence("last_30", "all");
  // Off for the company (404) or unreadable: the drop rule stays silent, the others still speak.
  const trend = useQuery({
    queryKey: ["home", "team-trend"],
    queryFn: () => api.get<TrendPayload>("/team/adherence/trend"),
    retry: false,
    staleTime: FIVE_MINUTES,
  });

  const data = team.data;
  const reps = data?.reps ?? [];
  const quiet = Boolean(data) && (reps.length === 0 || !data?.attempts);
  const signals = data
    ? teamSignals({
        reps: signalReps(reps, trend.data?.coverage === "complete" ? trend.data : null),
        diagnosis: summaryDiagnosis({ attempts: data.attempts ?? 0, adherence: data.adherence, processHealth: data.process_health ?? [] }),
      })
    : [];

  let body;
  if (team.isLoading || (data && trend.isLoading)) {
    body = (
      <div className="space-y-2" aria-busy="true">
        {[0, 1, 2].map((key) => (
          <Skeleton key={key} className="h-9 w-full motion-reduce:animate-none" />
        ))}
      </div>
    );
  } else if (team.isError || !data) {
    body = (
      <div className="space-y-3" role="alert">
        <p className={THEME_TOKENS.typography.body}>{p.teamReadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void team.refetch()}>
          {p.retry}
        </Button>
      </div>
    );
  } else if (quiet) {
    body = (
      <p className="flex items-start gap-2.5 text-[14px] text-foreground">
        <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/40" aria-hidden />
        {p.home.teamQuiet}
      </p>
    );
  } else if (!signals.length) {
    body = <p className={THEME_TOKENS.typography.body}>{p.home.noAlerts}</p>;
  } else {
    body = (
      <ul className="-mx-2 space-y-0.5">
        {signals.map((signal) => {
          const words = signalCopy(signal, p);
          const button = (
            <button
              type="button"
              onClick={() => onAsk(words.question)}
              className="flex w-full items-start gap-2.5 rounded-lg px-2 py-1.5 text-left text-[14px] leading-snug text-foreground transition-colors duration-150 hover:bg-secondary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
            >
              <span
                className={`mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full ${signal.tone === "warn" ? "bg-warning" : "bg-muted-foreground/40"}`}
                aria-hidden
              />
              {words.text}
            </button>
          );
          return (
            <li key={signal.id}>
              {words.evidence ? (
                <Tooltip>
                  <TooltipTrigger asChild>{button}</TooltipTrigger>
                  <TooltipContent side="left" className="max-w-[260px] whitespace-normal rounded-xl leading-snug">
                    {words.evidence}
                  </TooltipContent>
                </Tooltip>
              ) : (
                button
              )}
            </li>
          );
        })}
      </ul>
    );
  }

  const invite = Boolean(data) && reps.length === 0;
  return (
    <section aria-labelledby="home-rail-team" className="space-y-3">
      <h2 id="home-rail-team" className={THEME_TOKENS.typography.sectionTitle}>
        {p.home.team}
      </h2>
      {body}
      <Link
        to={invite ? INVITE : TEAM}
        className="inline-flex items-center gap-1 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
      >
        {invite ? p.home.inviteTeam : p.home.seeTeam}
        <ArrowRight aria-hidden className="h-3.5 w-3.5" />
      </Link>
    </section>
  );
}
