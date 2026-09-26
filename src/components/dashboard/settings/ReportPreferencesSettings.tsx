import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { reportKeys, reportsApi, type ReportPreferences } from "@/lib/api/reports";

type ReportKey = keyof ReportPreferences;

/** One switch per report the backend offers this person. Nothing offered, nothing rendered. */
export const ReportPreferencesSettings = () => {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: reportKeys.preferences, queryFn: () => reportsApi.preferences() });
  const save = useMutation({
    mutationFn: (changes: ReportPreferences) => reportsApi.savePreferences(changes),
    onSuccess: (updated) => queryClient.setQueryData(reportKeys.preferences, updated),
    onError: () => toast.error(t.product.reportPrefSaveFailed),
  });

  const labels: Record<ReportKey, string> = {
    daily: t.product.reportPrefDaily,
    weekly: t.product.reportPrefWeekly,
    team: t.product.reportPrefTeam,
  };
  const keys = (["daily", "weekly", "team"] as ReportKey[]).filter((key) => data?.[key] !== undefined);
  if (!keys.length) return null;

  return (
    <div id="report-preferences" className="space-y-3 border-t border-border/60 pt-5">
      <h3 className={THEME_TOKENS.typography.sectionTitle}>{t.product.reportsLabel}</h3>
      {keys.map((key) => (
        <label key={key} className="flex items-center justify-between gap-4 text-sm">
          <span>{labels[key]}</span>
          <Switch
            checked={Boolean(data?.[key])}
            disabled={save.isPending}
            onCheckedChange={(checked) => save.mutate({ [key]: checked })}
          />
        </label>
      ))}
    </div>
  );
};
