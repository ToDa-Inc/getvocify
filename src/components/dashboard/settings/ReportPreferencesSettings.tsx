import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { SettingsRow, SettingsSection } from "@/components/ui/settings-card";
import { Switch } from "@/components/ui/switch";
import { useLanguage } from "@/lib/i18n";
import { reportKeys, reportsApi, type ReportPreferences } from "@/lib/api/reports";

type ReportKey = keyof ReportPreferences;

/** One row per report the backend offers this person. Nothing offered, nothing rendered. */
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
    <SettingsSection id="report-preferences" label={t.product.reportsLabel}>
      {keys.map((key) => {
        // T13: the team weekly report is fixed for owner/admin - shown, never toggled.
        const fixed = key === "team";
        return (
          <SettingsRow key={key} title={labels[key]}>
            <Switch
              checked={Boolean(data?.[key])}
              disabled={fixed || save.isPending}
              onCheckedChange={fixed ? undefined : (checked) => save.mutate({ [key]: checked })}
              aria-label={labels[key]}
            />
          </SettingsRow>
        );
      })}
    </SettingsSection>
  );
};
