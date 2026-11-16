import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { SUGGESTIONS_QUERY, suggestionsApi, type SuggestionKind } from "@/features/playbooks/suggestionsApi";
import type { HosPeriod } from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { formatPercent } from "@/lib/rep-coaching";
import { displayName, hasRate, heatTone, weakestStep, type HeatTone, type TeamCoaching as TeamCoachingBody } from "@/lib/team-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const HEAT: Record<HeatTone, string> = {
  high: "bg-success/15 text-success",
  mid: "bg-warning/15 text-warning",
  low: "bg-destructive/10 text-destructive",
  few: "bg-secondary text-muted-foreground",
  none: "text-muted-foreground/50",
};
const DOT: Record<SuggestionKind, string> = { objection: "bg-warning", question: "bg-foreground/40", worked: "bg-success", opportunity: "bg-beige" };
// What needs the head of sales: a few, never a list to work through (that is Sugerencias).
const ATTENTION = 3;

function Head({ id, title, aside }: { id: string; title: string; aside?: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <h2 id={id} className={THEME_TOKENS.typography.sectionTitle}>{title}</h2>
      {aside}
    </div>
  );
}

/** «Lo que pide atención»: the few suggestions of this call type that cost most, each opening in Sugerencias, and what the
 * reps conceded beyond the offer. */
export function Attention({ data }: { data: TeamCoachingBody }) {
  const { t } = useLanguage();
  const p = t.product;
  const c = p.pb2.suggestions;
  const suggestions = useQuery({ queryKey: SUGGESTIONS_QUERY, queryFn: suggestionsApi.list, retry: false, staleTime: 60_000 });
  // What is unresolved comes first (an objection, a question, an opening); a move that worked waits after them.
  const rank: Record<SuggestionKind, number> = { objection: 0, question: 1, opportunity: 2, worked: 3 };
  const own = (suggestions.data?.suggestions ?? []).filter((s) => s.motion === data.type).sort((a, b) => rank[a.kind] - rank[b.kind]);
  // A concession is the head of sales' business only when it goes below what the company's material calls normal.
  const concessions = (data.findings?.concessions ?? []).filter((item) => item.normal).slice(0, 2);
  if (!own.length && !concessions.length) return null;
  const context = (s: (typeof own)[number]) => s.why || s.examples.find((e) => e.summary)?.summary || null;
  return (
    <section aria-labelledby="team-attention" className="space-y-3 px-3">
      <Head
        id="team-attention"
        title={p.teamAttention}
        aside={
          own.length > ATTENTION ? (
            <Link to="/dashboard/playbook?view=suggestions" className="inline-flex items-center gap-0.5 text-[13px] text-muted-foreground hover:text-foreground">
              {p.teamAttentionAll.replace("{count}", String(own.length))}
              <ChevronRight aria-hidden className="h-3.5 w-3.5" strokeWidth={1.5} />
            </Link>
          ) : null
        }
      />
      <ul className="divide-y divide-border/50 border-y border-border/50">
        {own.slice(0, ATTENTION).map((s) => (
          <li key={s.key}>
            <Link to={`/dashboard/playbook?view=suggestions&open=${s.key}`} className={cn("flex items-start gap-3 py-3", THEME_TOKENS.interaction.rowHover)}>
              <span aria-hidden className={cn("mt-2 h-2 w-2 shrink-0 rounded-full", DOT[s.kind])} />
              <span className="sr-only">{c.kinds[s.kind]}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-[14.5px] font-medium text-foreground">{s.title}</span>
                {context(s) ? <span className="line-clamp-1 text-[13px] text-muted-foreground">{context(s)}</span> : null}
              </span>
              {s.count > 1 ? <span className="shrink-0 pt-0.5 text-[12.5px] tabular-nums text-foreground/70">×{s.count}</span> : null}
              <ChevronRight aria-hidden className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.5} />
            </Link>
          </li>
        ))}
        {concessions.map((item) => (
          <li key={`${item.memo_id}-${item.what}`}>
            <Link to={`/dashboard/memos/${item.memo_id}`} className={cn("flex items-start gap-3 py-3", THEME_TOKENS.interaction.rowHover)}>
              <span aria-hidden className="mt-2 h-2 w-2 shrink-0 rounded-full bg-foreground/30" />
              <span className="min-w-0 flex-1">
                <span className="block text-[14.5px] font-medium text-foreground">{item.what}</span>
                <span className="line-clamp-1 text-[13px] text-muted-foreground">
                  {[p.teamConcessionKind, displayName(item.rep), item.normal].filter(Boolean).join(" · ")}
                </span>
              </span>
              <ChevronRight aria-hidden className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.5} />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** One row per rep, the heart of Equipo: their conversations, meetings, how much of the playbook they follow, and the
 * step they do least, as the first thing to coach. A row opens the rep. */
export function Reps({ data, period }: { data: TeamCoachingBody; period: HosPeriod }) {
  const { t } = useLanguage();
  const p = t.product;
  const { follow } = data;
  if (!follow.reps.length) return null;
  // Like the tile above: no meetings marked by anyone, no column of zeros.
  const meetings = follow.reps.some((rep) => rep.meetings > 0);
  return (
    <section aria-labelledby="team-reps" className="space-y-3 px-3">
      <Head id="team-reps" title={p.teamRepsHeading} />
      <div className="overflow-x-auto">
        <table className="w-full text-left" data-testid="team-reps">
          <thead>
            <tr className="text-xs text-muted-foreground">
              <th scope="col" className="pb-2 font-normal">{p.teamRepColumn}</th>
              <th scope="col" className="w-28 pb-2 text-right font-normal">{p.coachKpiConversations}</th>
              {meetings ? <th scope="col" className="w-24 pb-2 text-right font-normal">{p.teamMeetingsColumn}</th> : null}
              <th scope="col" className="w-24 pb-2 text-center font-normal">{p.teamPlaybookColumn}</th>
              <th scope="col" className="pb-2 pl-6 font-normal">{p.teamWeakestColumn}</th>
              <th aria-hidden className="w-6" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50 border-y border-border/50">
            {follow.reps.map((rep) => {
              const weakest = weakestStep(rep, follow.steps);
              const enough = hasRate(rep.evaluated, rep.adherence);
              const to = `/dashboard/insights/rep/${rep.user_id}?period=${period}`;
              return (
                <tr key={rep.user_id} className={cn("group", THEME_TOKENS.interaction.rowHover)}>
                  <td className="py-3">
                    <Link to={to} className="text-[14.5px] font-medium text-foreground hover:underline underline-offset-4">
                      {displayName(rep.name)}
                    </Link>
                  </td>
                  <td className="py-3 text-right text-[14px] tabular-nums text-foreground">{rep.conversations}</td>
                  {meetings ? <td className="py-3 text-right text-[14px] tabular-nums text-foreground">{rep.meetings}</td> : null}
                  <td className="py-3 text-center">
                    <span className={cn("inline-block min-w-[3.5rem] rounded-md px-2 py-1 text-[13px] font-semibold tabular-nums", HEAT[enough ? heatTone({ applicable: rep.evaluated, rate: rep.adherence }) : "none"])}>
                      {enough ? formatPercent(rep.adherence) : "—"}
                    </span>
                  </td>
                  <td className="py-3 pl-6 text-[13.5px] text-muted-foreground">
                    {weakest ? (
                      <span>
                        {weakest.label} <span className="tabular-nums text-destructive">{formatPercent(weakest.rate)}</span>
                      </span>
                    ) : null}
                  </td>
                  <td className="py-3 text-right">
                    <Link to={to} aria-label={displayName(rep.name)} className="inline-flex text-muted-foreground group-hover:text-foreground">
                      <ChevronRight aria-hidden className="h-4 w-4" strokeWidth={1.5} />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
