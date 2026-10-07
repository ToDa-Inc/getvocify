import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import { crmApi } from "@/lib/api/crm";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const preferenceKey = ["crm-call-recordings-preference"] as const;

/** Whether calls the rep's own dialer saves in the CRM become memos. Off for a rep who records
 * with the Vocify app: the call is already a memo, so its CRM recording is never processed twice. */
export const CallRecordingsSettings = () => {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: preferenceKey, queryFn: () => crmApi.callRecordingsPreference() });
  const save = useMutation({
    mutationFn: (process: boolean) => crmApi.setCallRecordingsPreference(process),
    onMutate: (process) => queryClient.setQueryData(preferenceKey, { process }),
    onError: () => {
      queryClient.invalidateQueries({ queryKey: preferenceKey });
      toast.error(t.product.callRecordingsSaveFailed);
    },
  });

  return (
    <div className="flex items-start justify-between gap-6">
      <div className="space-y-1">
        <p className={THEME_TOKENS.typography.sectionRail}>{t.product.callRecordingsHeading}</p>
        <p className="text-sm text-muted-foreground">{t.product.callRecordingsHelper}</p>
      </div>
      <Switch
        checked={data?.process ?? true}
        disabled={!data}
        onCheckedChange={(process) => save.mutate(process)}
        aria-label={t.product.callRecordingsHeading}
      />
    </div>
  );
};
