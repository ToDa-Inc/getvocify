import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import { memosApi } from "@/features/memos/api";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

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
    <div className="flex items-start justify-between gap-6 border-t border-border/60 pt-5">
      <div className="space-y-1">
        <p className={THEME_TOKENS.typography.sectionRail}>{t.product.followupSuggestHeading}</p>
        <p className="text-sm text-muted-foreground">{t.product.followupSuggestHelper}</p>
      </div>
      <Switch
        checked={data?.suggest ?? true}
        disabled={!data}
        onCheckedChange={(suggest) => save.mutate(suggest)}
        aria-label={t.product.followupSuggestHeading}
      />
    </div>
  );
};
