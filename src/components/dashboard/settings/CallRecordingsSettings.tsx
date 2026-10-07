import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import { crmApi } from "@/lib/api/crm";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const preferenceKey = ["crm-call-recordings-preference"] as const;

/** Whether calls the rep's own dialer saves in the CRM become memos. Off by default: the rep records
 * with the Vocify app, so the call is already a memo and its CRM recording is never processed twice. */
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
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>{t.product.callRecordingsHeading}</h3>
        <p className="text-xs text-muted-foreground mt-1">{t.product.callRecordingsHelper}</p>
      </div>
      <Switch
        checked={data?.process ?? false}
        disabled={!data}
        onCheckedChange={(process) => save.mutate(process)}
        aria-label={t.product.callRecordingsHeading}
      />
    </div>
  );
};
