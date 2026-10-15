import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Mail } from "lucide-react";
import { SettingsRow } from "@/components/ui/settings-card";
import { Switch } from "@/components/ui/switch";
import { memosApi } from "@/features/memos/api";
import { useLanguage } from "@/lib/i18n";

const preferenceKey = ["followup-preference"] as const;

/** Whether Vocify drafts a follow-up email after each call. Off: no draft is generated. */
export const FollowupSuggestSettings = () => {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: preferenceKey, queryFn: () => memosApi.followupPreference() });
  const save = useMutation({
    mutationFn: (suggest: boolean) => memosApi.setFollowupPreference(suggest),
    onMutate: (suggest) => queryClient.setQueryData(preferenceKey, { suggest }),
    onError: () => {
      queryClient.invalidateQueries({ queryKey: preferenceKey });
      toast.error(t.product.followupSuggestSaveFailed);
    },
  });

  return (
    <SettingsRow icon={Mail} title={t.product.followupSuggestHeading} description={t.product.followupSuggestHelper}>
      <Switch
        checked={data?.suggest ?? true}
        disabled={!data}
        onCheckedChange={(suggest) => save.mutate(suggest)}
        aria-label={t.product.followupSuggestHeading}
      />
    </SettingsRow>
  );
};
