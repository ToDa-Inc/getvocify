import { Link, useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { composeHome } from "@shared/ui/home.js";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth";
import { CRM_PROVIDER_CONFIGS, type CRMProvider } from "@/features/integrations/types";
import { useContactPriorities } from "@/features/today/hooks/useContactPriorities";
import { useHomeReads } from "@/features/today/hooks/useHomeReads";
import { useTodayCardActions } from "@/features/today/hooks/useTodayCardActions";
import { railCounts, type RailCounts } from "@/lib/home-rail";
import { useLanguage } from "@/lib/i18n";
import type { ProductTranslations } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const TODAY = "/dashboard/today";
const rowClass =
  "flex items-baseline gap-3 rounded-lg px-2 py-1.5 text-[14px] text-foreground transition-colors duration-150 hover:bg-secondary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none";

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
 * The rep's day, condensed: today's meetings and how much waits in each part of Hoy. Built from the
 * same reads and the same composition as /dashboard/today, so the numbers match what Hoy shows there.
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
  const counts = railCounts(view);
  const rows = countRows(counts, copy);

  let body;
  if (view.state === "loading") {
    body = (
      <div className="space-y-2" aria-busy="true">
        {[0, 1, 2].map((key) => (
          <Skeleton key={key} className="h-7 w-full motion-reduce:animate-none" />
        ))}
      </div>
    );
  } else if (view.state === "error") {
    body = (
      <div className="space-y-3" role="alert">
        <p className={THEME_TOKENS.typography.body}>{copy.today_prepare_failed}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void query.refetch()}>
          {copy.retry}
        </Button>
      </div>
    );
  } else if (view.state === "connect" || view.state === "no_assigned") {
    // The same card Hoy shows: whoever can fix it gets the button, a rep is told who can.
    const connect = view.state === "connect";
    body = (
      <div className="space-y-3">
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
  } else if (!counts.meetings.length && !rows.length) {
    body = <p className={THEME_TOKENS.typography.body}>{copy.home.allClear}</p>;
  } else {
    body = (
      <div className="space-y-3">
        {counts.meetings.length ? (
          <ul aria-label={copy.home_meetings} className="-mx-2">
            {counts.meetings.map(({ item, time, past }) => {
              const name = item.reason || item.contact_name || copy.today_unknown_contact;
              return (
                <li key={item.id ?? item.dedupe_key ?? name}>
                  <Link to={TODAY} className={`${rowClass} ${past ? "opacity-60" : ""}`}>
                    <span className="w-11 shrink-0 tabular-nums">{time ?? copy.home_meeting_no_time}</span>
                    <span className="min-w-0 truncate" title={item.company_name ? `${name} · ${item.company_name}` : name}>
                      {name}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        ) : null}
        {rows.length ? (
          <ul className={counts.meetings.length ? "-mx-2 border-t border-[hsl(var(--hairline))] pt-2" : "-mx-2"}>
            {rows.map((row) => (
              <li key={row.key}>
                <Link to={TODAY} className={rowClass}>
                  <span className="min-w-0 flex-1 truncate">{row.label}</span>
                  <span className="tabular-nums text-muted-foreground">{row.count}</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }

  return (
    <section aria-labelledby="home-rail-today" className="space-y-3">
      <h2 id="home-rail-today" className={THEME_TOKENS.typography.sectionTitle}>
        {copy.todayTitle}
      </h2>
      {body}
      <Link
        to={TODAY}
        className="inline-flex items-center gap-1 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
      >
        {copy.home.seeMyDay}
        <ArrowRight aria-hidden className="h-3.5 w-3.5" />
      </Link>
    </section>
  );
}
