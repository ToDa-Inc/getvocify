import { FilterMenu } from "@/features/interactions/components/FilterMenu";
import { Segmented } from "@/components/ui/segmented";
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
      <FilterMenu
        label={p.hosPeriodLabel}
        value={period}
        choices={HOS_PERIODS.map((option) => ({ value: option.value, label: String(p[option.labelKey]) }))}
        onChange={(next) => onPeriod(next as HosPeriod)}
      />
      {showRoles ? (
        <Segmented<HosSalesRole>
          value={salesRole}
          onValueChange={onSalesRole}
          options={ROLE_FILTERS.map((option) => ({
            value: option.value,
            label: p[option.key],
          }))}
          aria-label={p.hosRoleLabel}
        />
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
