import { Link, useNavigate } from "react-router-dom";
import { composeHome } from "@shared/ui/home.js";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth";
import { CRM_PROVIDER_CONFIGS, type CRMProvider } from "@/features/integrations/types";
import { useContactPriorities } from "@/features/today/hooks/useContactPriorities";
import { useHomeReads } from "@/features/today/hooks/useHomeReads";
import { useTodayCardActions } from "@/features/today/hooks/useTodayCardActions";
import { railState, type RailCounts } from "@/lib/home-rail";
import { useLanguage } from "@/lib/i18n";
import type { ProductTranslations } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const TODAY = "/dashboard/today";
const chipClass =
  "inline-flex max-w-full items-baseline gap-2 rounded-full border border-border bg-card px-3.5 py-1.5 text-[13.5px] text-foreground transition-colors duration-150 hover:border-beige/40 hover:bg-secondary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none";

/** `undefined` while the first read is in flight, `null` once it failed without data (as on Hoy). */
function settled<T>(query: { data: T | undefined; isError: boolean }): T | null | undefined {
  return query.data ?? (query.isError ? null : undefined);
}

function countRows(counts: RailCounts, copy: ProductTranslations) {
  return [
    { key: "needs_ok", label: copy.home_needs_ok, count: counts.needsOk },
    { key: "tasks", label: copy.home_tasks, count: counts.tasks },
    { key: "followups", label: copy.home_followups, count: counts.followups },
    { key: "new", label: copy.home_new, count: counts.fresh },
    { key: "calls", label: copy.home_calls, count: counts.calls },
  ].filter((row) => row.count > 0);
}

/**
 * Only for a company with the rep workspace (REP_WORKSPACE_ENABLED): /followups, /today/upcoming and
 * /today/done 404 without it, and so does the Hoy these rows link to.
 *
 * The rep's day, condensed under Inicio's composer: today's meetings and how much waits in each part
 * of Hoy, one chip each in a row, every chip opening /dashboard/today. Built from the same reads and
 * the same composition as /dashboard/today, so the numbers match what Hoy shows there.
 */
export function RepRail() {
  const { t } = useLanguage();
  const copy = t.product;
  const navigate = useNavigate();
  const { user } = useAuth();
  const { query, acted, connected, provider } = useTodayCardActions({ fresh: true });
  const priorities = useContactPriorities({ fresh: true });
  const reads = useHomeReads();

  const view = composeHome({
    today: settled(query),
    todayStale: query.isError && Boolean(query.data),
    acted,
    priorities: settled(priorities),
    followups: settled(reads.followups),
    reviews: reads.reviews.isError ? null : reads.reviews.data,
    upcoming: settled(reads.upcoming),
    done: settled(reads.done),
    connected: connected ?? undefined,
    role: user?.company?.role ?? "member",
    crm: provider ? CRM_PROVIDER_CONFIGS[provider as CRMProvider]?.name ?? null : null,
    now: Date.now(),
    locale: copy.hourLocale,
    sdrSections: Boolean(user?.company?.features?.includes("HOY_SDR_SECTIONS_ENABLED")),
  });
  const { state, counts, incomplete } = railState(view);
  const rows = countRows(counts, copy);
  const retryAll = () => {
    void query.refetch();
    void priorities.refetch();
    for (const read of Object.values(reads)) void read.refetch();
  };

  if (state === "loading") {
    return (
      <div className="flex flex-wrap justify-center gap-2" aria-busy="true">
        {[0, 1, 2].map((key) => (
          <Skeleton key={key} className="h-8 w-28 rounded-full motion-reduce:animate-none" />
        ))}
      </div>
    );
  }
  if (state === "error" || state === "partial") {
    return (
      <div className="flex flex-wrap items-center justify-center gap-3" role="alert">
        <p className={THEME_TOKENS.typography.body}>{state === "error" ? copy.today_prepare_failed : copy.today_incomplete}</p>
        <Button type="button" variant="outline" size="sm" onClick={retryAll}>
          {copy.retry}
        </Button>
      </div>
    );
  }
  if (state === "connect" || state === "no_assigned") {
    // The same card Hoy shows: whoever can fix it gets the button, a rep is told who can.
    const connect = state === "connect";
    return (
      <div className="flex flex-wrap items-center justify-center gap-3 text-center">
        <p className="text-[14px] text-foreground">{connect ? copy.today_connect_title : copy.title_no_assigned}</p>
        {view.canManage ? (
          <Button type="button" variant="outline" size="sm" onClick={() => navigate("/dashboard/settings/integrations")}>
            {connect ? copy.connect_crm : copy.map_owners}
          </Button>
        ) : (
          <p className={THEME_TOKENS.typography.body}>{connect ? copy.today_connect_admin_detail : copy.review_assignment}</p>
        )}
      </div>
    );
  }
  if (state === "clear") {
    return <p className={`${THEME_TOKENS.typography.body} text-center`}>{copy.home.allClear}</p>;
  }

  return (
    <section aria-label={copy.todayTitle} className="space-y-2">
      {incomplete ? (
        <p className="text-center text-[13px] text-muted-foreground">
          {copy.today_incomplete}
          {view.incompleteAt ? ` · ${view.incompleteAt}` : ""}
        </p>
      ) : null}
      <ul className="flex flex-wrap justify-center gap-2">
        {counts.meetings.map(({ item, time, past }) => {
          const name = item.reason || item.contact_name || copy.today_unknown_contact;
          return (
            <li key={item.id ?? item.dedupe_key ?? name} className="max-w-full">
              <Link
                to={TODAY}
                className={`${chipClass} ${past ? "opacity-60" : ""}`}
                title={item.company_name ? `${name} · ${item.company_name}` : name}
              >
                <span className="shrink-0 tabular-nums text-muted-foreground">{time ?? copy.home_meeting_no_time}</span>
                <span className="min-w-0 truncate">{name}</span>
              </Link>
            </li>
          );
        })}
        {rows.map((row) => (
          <li key={row.key}>
            <Link to={TODAY} className={chipClass}>
              <span>{row.label}</span>
              <span className="tabular-nums text-muted-foreground">{row.count}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
