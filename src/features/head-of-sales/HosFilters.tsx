import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { HOS_PERIODS, type HosPeriod, type HosSalesRole } from "@/lib/head-of-sales";

const ROLE_FILTERS: { value: HosSalesRole; key: "hosRoleAll" | "hosRoleSdr" | "hosRoleAe" }[] = [
  { value: "all", key: "hosRoleAll" },
  { value: "sdr", key: "hosRoleSdr" },
  { value: "ae", key: "hosRoleAe" },
];

/** One filter row for every Head of Sales page: period and position. */
export function HosFilters({
  period,
  salesRole,
  onPeriod,
  onSalesRole,
  showRoles,
}: {
  period: HosPeriod;
  salesRole: HosSalesRole;
  onPeriod: (value: HosPeriod) => void;
  onSalesRole: (value: HosSalesRole) => void;
  /** Only when the company uses SDR/AE positions; otherwise the filter would do nothing. */
  showRoles: boolean;
}) {
  const { t } = useLanguage();
  const p = t.product;
  return (
    <div className="flex flex-wrap items-center gap-3" data-testid="hos-filters">
      <select
        aria-label={p.hosPeriodLabel}
        className="rounded-full border border-border bg-card px-4 py-1.5 text-sm text-foreground"
        value={period}
        onChange={(event) => onPeriod(event.target.value as HosPeriod)}
      >
        {HOS_PERIODS.map((option) => (
          <option key={option.value} value={option.value}>
            {String(p[option.labelKey])}
          </option>
        ))}
      </select>
      {showRoles ? (
        <div role="group" aria-label={p.hosRoleLabel} className="inline-flex rounded-full border border-border bg-card p-1">
          {ROLE_FILTERS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={salesRole === option.value}
              onClick={() => onSalesRole(option.value)}
              className={`rounded-full px-3.5 py-1 text-xs transition-colors ${
                salesRole === option.value ? "bg-beige text-cream" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {p[option.key]}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function HosPageHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header className="space-y-1.5">
      <h1 className={THEME_TOKENS.typography.pageTitle}>{title}</h1>
      <p className={THEME_TOKENS.typography.body}>{subtitle}</p>
    </header>
  );
}
