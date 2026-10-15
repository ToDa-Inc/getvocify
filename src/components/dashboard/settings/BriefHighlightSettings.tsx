import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Sparkles } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SettingsRow } from "@/components/ui/settings-card";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import {
  briefPreferenceKeys,
  briefPreferencesApi,
  type BriefHighlightMode,
  type BriefPreference,
} from "@/lib/api/brief-preferences";

export const BriefHighlightSettings = () => {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const options = useMemo(
    (): { mode: BriefHighlightMode; label: string }[] => [
      { mode: "immediate", label: t.product.briefHighlightImmediate },
      { mode: "deferred", label: t.product.briefHighlightDeferred30 },
      { mode: "end_of_day", label: t.product.briefHighlightEndOfDay },
    ],
    [t.product],
  );
  const { data, isLoading, isError } = useQuery({
    queryKey: briefPreferenceKeys.current(),
    queryFn: () => briefPreferencesApi.get(),
  });
  const save = useMutation({
    mutationFn: (mode: BriefHighlightMode) => briefPreferencesApi.put({ highlight_mode: mode }),
    onSuccess: (updated: BriefPreference) => {
      queryClient.setQueryData(briefPreferenceKeys.current(), updated);
      toast.success(t.product.briefHighlightSaved);
    },
    onError: () => {
      toast.error(t.product.briefHighlightSaveFailed);
    },
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <VocifySpinner size={24} />
      </div>
    );
  }

  if (isError) {
    return (
      <p className="text-sm text-muted-foreground">{t.product.briefHighlightLoadFailed}</p>
    );
  }

  return (
    <SettingsRow icon={Sparkles} title={t.product.briefHighlightHeading} description={t.product.briefHighlightHelper}>
      <Select
        value={data?.highlight_mode}
        onValueChange={(mode) => save.mutate(mode as BriefHighlightMode)}
        disabled={save.isPending}
      >
        <SelectTrigger variant="chip" aria-label={t.product.briefHighlightWhenAria}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((opt) => (
            <SelectItem key={opt.mode} value={opt.mode}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </SettingsRow>
  );
};
