import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth";
import { AdherenceBreakdown } from "@/features/team-insights/components/AdherenceBreakdown";
import { AdherenceTrend } from "@/features/team-insights/components/AdherenceTrend";
import { ObjectionBreakdown } from "@/features/team-insights/components/ObjectionBreakdown";
import { HOS_DEFAULT_PERIOD, HOS_PERIODS, adherenceParams, type HosPeriod } from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { isManagerRole } from "@/lib/nav";
import {
  teamCrmCoverage,
  type ObjectionCategory,
  type TeamFilters,
  type TeamMetrics,
} from "@/lib/team-insights";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { api, ApiError } from "@/shared/lib/api-client";

type HandoffRow = {
  id: string;
  contact_id: string;
  status: string;
  created_at?: string;
  contact_name?: string | null;
  company_name?: string | null;
};
type RepDetail = {
  user_id: string;
  name?: string | null;
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

const HANDOFF_STATUS_KEYS = {
  active: "handoffStatusActive",
  closed: "handoffStatusClosed",
  cancelled: "handoffStatusCancelled",
} as const;

function HandoffList({ rows, empty }: { rows: HandoffRow[]; empty: string }) {
  const { t } = useLanguage();
  if (rows.length === 0) return <p className={THEME_TOKENS.typography.body}>{empty}</p>;
  const date = new Intl.DateTimeFormat(t.product.hourLocale, { day: "numeric", month: "short" });
  return (
    <ul className="space-y-1 text-sm">
      {rows.map((row) => {
        const statusKey = HANDOFF_STATUS_KEYS[row.status as keyof typeof HANDOFF_STATUS_KEYS];
        const when = row.created_at ? date.format(new Date(row.created_at)) : null;
        const who = [row.contact_name || row.contact_id, row.company_name].filter(Boolean).join(" · ");
        return (
          <li key={row.id} className="flex items-center justify-between gap-2">
            <span className="min-w-0 truncate text-foreground">{who}</span>
            <span className="shrink-0 text-muted-foreground">
              {[when, statusKey ? t.product[statusKey] : row.status].filter(Boolean).join(" · ")}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export default function TeamRepDetailPage() {
  const { t } = useLanguage();
  const { user } = useAuth();
  const { userId = "" } = useParams<{ userId: string }>();
  const role = user?.company?.role ?? "member";
  const isManager = isManagerRole(role);
  const allowed = isManager || user?.company?.visibility === "team";
  const [searchParams] = useSearchParams();
  // The Head of Sales arrives from a table with ?period=; a rep-side reader keeps the week.
  const requested = HOS_PERIODS.find((entry) => entry.value === searchParams.get("period"));
  const period: HosPeriod = requested?.value ?? HOS_DEFAULT_PERIOD;
  const periodLabelKey = HOS_PERIODS.find((entry) => entry.value === period)?.labelKey ?? "hosPeriodMonth";
  const filters: TeamFilters = { period: "week", motion: null, userId };
  const p = t.product;

  const adherenceQuery = useQuery({
    queryKey: ["team-adherence", filters, isManager ? period : "week"],
    queryFn: () =>
      api.get<AdherencePayload>(
        `/team/adherence?${adherenceParams({ manager: isManager, period, salesRole: "all", userId, motion: null })}`,
      ),
    enabled: allowed && Boolean(userId),
    retry: false,
  });
  const repQuery = useQuery({
    queryKey: ["team-rep-detail", userId],
    queryFn: () => api.get<RepDetail>(`/team/rep/${encodeURIComponent(userId)}`),
    enabled: allowed && Boolean(userId),
    retry: false,
  });

  // Lista 4 E5: a rep who can't read the team panel has Coach instead of Team.
  if (user && !allowed) return <Navigate to="/dashboard/coach" replace />;
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
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <h1 className={THEME_TOKENS.typography.pageTitle}>{repQuery.data?.name || p.teamRepDetailTitle}</h1>
          {repQuery.data?.name ? (
            <p className={THEME_TOKENS.typography.capsLabel}>
              {p.teamRepDetailTitle}
              {isManager ? ` · ${p[periodLabelKey]}` : ""}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-4">
          {isManager ? (
            <Link
              className="rounded-full border border-border px-3.5 py-1.5 text-sm text-foreground hover:bg-secondary/40"
              to={`/dashboard/memos?author=${encodeURIComponent(userId)}`}
            >
              {p.hosSeeCalls}
            </Link>
          ) : null}
          <Link className="text-sm underline text-foreground" to="/dashboard/insights">
            {p.teamRepDetailBack}
          </Link>
        </div>
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
