import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth";
import { AdherenceBreakdown } from "@/features/team-insights/components/AdherenceBreakdown";
import { AdherenceTrend } from "@/features/team-insights/components/AdherenceTrend";
import { ObjectionBreakdown } from "@/features/team-insights/components/ObjectionBreakdown";
import { useLanguage } from "@/lib/i18n";
import {
  teamCrmCoverage,
  type ObjectionCategory,
  type TeamFilters,
  type TeamMetrics,
} from "@/lib/team-insights";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { api, ApiError } from "@/shared/lib/api-client";

type HandoffRow = { id: string; contact_id: string; status: string; created_at?: string };
type RepDetail = {
  user_id: string;
  sales_role: "sdr" | "ae" | "general" | null;
  handoffs: { as_sdr: HandoffRow[]; as_ae: HandoffRow[] } | null;
};

type AdherencePayload = {
  adherence: number | null;
  met_steps: number;
  applicable_steps: number;
  coverage: number | null;
  crm_coverage?: "complete" | "partial";
  won?: number | null;
  lost?: number | null;
  unresolved_wins?: number;
  sample_limited?: boolean;
  attempts?: number;
  connected?: number;
  meetings?: number;
  objection_categories?: ObjectionCategory[];
  review?: { memo_id: string; line: string }[];
};

function HandoffList({ rows, empty }: { rows: HandoffRow[]; empty: string }) {
  if (rows.length === 0) return <p className={THEME_TOKENS.typography.body}>{empty}</p>;
  return (
    <ul className="space-y-1 text-sm">
      {rows.map((row) => (
        <li key={row.id} className="flex items-center justify-between gap-2">
          <span className="text-foreground">{row.contact_id}</span>
          <span className="text-muted-foreground">{row.status}</span>
        </li>
      ))}
    </ul>
  );
}

export default function TeamRepDetailPage() {
  const { t } = useLanguage();
  const { user } = useAuth();
  const { userId = "" } = useParams<{ userId: string }>();
  const role = user?.company?.role ?? "member";
  const allowed = role === "owner" || role === "admin" || user?.company?.visibility === "team";
  const filters: TeamFilters = { period: "week", motion: null, userId };
  const p = t.product;

  const adherenceQuery = useQuery({
    queryKey: ["team-adherence", filters],
    queryFn: () => api.get<AdherencePayload>(`/team/adherence?user_id=${encodeURIComponent(userId)}`),
    enabled: allowed && Boolean(userId),
    retry: false,
  });
  const repQuery = useQuery({
    queryKey: ["team-rep-detail", userId],
    queryFn: () => api.get<RepDetail>(`/team/rep/${encodeURIComponent(userId)}`),
    enabled: allowed && Boolean(userId),
    retry: false,
  });

  if (!allowed) {
    return (
      <main className={`max-w-3xl mx-auto space-y-4 ${THEME_TOKENS.motion.fadeIn}`}>
        <p>{p.teamDenied}</p>
      </main>
    );
  }

  const data = adherenceQuery.data;
  const metrics: TeamMetrics | null = data
    ? {
        attempts: typeof data.attempts === "number" ? data.attempts : null,
        connected: typeof data.connected === "number" ? data.connected : null,
        meetings: typeof data.meetings === "number" ? data.meetings : null,
        won: data.won ?? null,
        lost: data.lost ?? null,
        unresolvedWins: data.unresolved_wins ?? 0,
        adherence: data.adherence,
        met: data.met_steps,
        applicable: data.applicable_steps,
        coverageCrm: teamCrmCoverage(data.crm_coverage),
        sampleLimited: data.sample_limited === true,
      }
    : null;

  // 403/404 while a handoffs read stays optional (HANDOFF_ENABLED off): render everything else.
  const repDetailUnavailable =
    repQuery.error instanceof ApiError && (repQuery.error.status === 404 || repQuery.error.status === 403);
  const handoffs = repQuery.data?.handoffs ?? null;

  return (
    <main className={`max-w-3xl mx-auto space-y-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className="flex items-center justify-between">
        <h1 className={THEME_TOKENS.typography.pageTitle}>{p.teamRepDetailTitle}</h1>
        <Link className="text-sm underline text-foreground" to="/dashboard/insights">
          {p.teamRepDetailBack}
        </Link>
      </div>
      {adherenceQuery.isLoading ? <p className={THEME_TOKENS.typography.body}>{p.teamLoading}</p> : null}
      {adherenceQuery.isError ? <p className={THEME_TOKENS.typography.body}>{p.teamReadFailed}</p> : null}
      {metrics ? (
        <>
          <AdherenceBreakdown metrics={metrics}>
            <AdherenceTrend filters={filters} />
          </AdherenceBreakdown>
          <ObjectionBreakdown
            categories={data?.objection_categories ?? []}
            sampleLimited={data?.sample_limited === true}
          />
          {(data?.review?.length ?? 0) > 0 ? (
            <section className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-3 p-5`}>
              <h2 className={THEME_TOKENS.typography.sectionTitle}>{p.teamReviewTitle}</h2>
              <ul className="space-y-2">
                {data?.review?.map((item) => (
                  <li key={item.memo_id}>
                    <Link className="text-[15px] leading-relaxed text-foreground" to={`/dashboard/memos/${item.memo_id}`}>
                      {item.line}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </>
      ) : null}
      {!repDetailUnavailable && handoffs ? (
        <section className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-4 p-5`}>
          <h2 className={THEME_TOKENS.typography.sectionTitle}>{p.teamRepHandoffsHeading}</h2>
          <div>
            <h3 className={THEME_TOKENS.typography.capsLabel}>{p.teamRepHandoffsPassed}</h3>
            <HandoffList rows={handoffs.as_sdr} empty={p.teamRepHandoffsNone} />
          </div>
          <div>
            <h3 className={THEME_TOKENS.typography.capsLabel}>{p.teamRepHandoffsReceived}</h3>
            <HandoffList rows={handoffs.as_ae} empty={p.teamRepHandoffsNone} />
          </div>
        </section>
      ) : null}
    </main>
  );
}
