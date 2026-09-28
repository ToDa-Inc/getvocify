import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Textarea } from "@/components/ui/textarea";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { useLanguage } from "@/lib/i18n";
import { writingSampleKeys, writingSamplesApi, type WritingSamples } from "@/lib/api/writing-samples";
import {
  MAX_CHARS,
  countLabel,
  isDirty,
  samplesPayload,
  shortWarning,
  slotsFor,
  tooShort,
} from "@/lib/writing-samples";

/** Pasted emails the follow-up draft imitates. Collapsed: it is set once, not used daily. */
export const WritingSamplesSettings = () => {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: writingSampleKeys.current(),
    queryFn: () => writingSamplesApi.get(),
  });
  const saved = data?.samples ?? [];
  const [drafts, setDrafts] = useState<string[]>(() => slotsFor([]));
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (data) {
      setDrafts(slotsFor(data.samples));
    }
  }, [data]);

  const save = useMutation({
    mutationFn: (samples: string[]) => writingSamplesApi.put(samples),
    onSuccess: (updated: WritingSamples) => {
      queryClient.setQueryData(writingSampleKeys.current(), updated);
      toast.success(t.product.writingSamplesSaved);
    },
    onError: () => {
      toast.error(t.product.writingSamplesSaveFailed);
    },
  });

  const short = shortWarning(drafts, checked);
  const dirty = data != null && isDirty(drafts, saved);
  const count = countLabel(saved.length, t.product.writingSamplesCountOne, t.product.writingSamplesCountMany);

  return (
    <Collapsible className="border-t border-border/60 pt-5">
      <CollapsibleTrigger className="group flex w-full items-center justify-between gap-4 text-left">
        <span className={THEME_TOKENS.typography.sectionRail}>{t.product.writingSamplesHeading}</span>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          {count}
          <ChevronDown className="h-4 w-4 transition-transform group-data-[state=open]:rotate-180" />
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 pt-3">
        {isLoading ? (
          <div className="flex justify-center py-6">
            <VocifySpinner size={20} />
          </div>
        ) : isError ? (
          <p className="text-sm text-muted-foreground">{t.product.writingSamplesLoadFailed}</p>
        ) : (
          <>
            <p className="text-xs text-muted-foreground">{t.product.writingSamplesHelper}</p>
            {drafts.map((draft, i) => (
              <Textarea
                key={i}
                value={draft}
                maxLength={MAX_CHARS}
                rows={3}
                aria-label={t.product.writingSamplesSlot.replace("{n}", String(i + 1))}
                placeholder={t.product.writingSamplesSlot.replace("{n}", String(i + 1))}
                onBlur={() => setChecked(true)}
                onChange={(event) =>
                  setDrafts((current) => current.map((value, j) => (j === i ? event.target.value : value)))
                }
              />
            ))}
            <div className="flex items-center justify-end gap-4">
              {short && <p className="text-xs text-destructive">{t.product.writingSamplesTooShort}</p>}
              <Button
                onClick={() => {
                  if (tooShort(drafts)) {
                    setChecked(true);
                    return;
                  }
                  save.mutate(samplesPayload(drafts));
                }}
                disabled={!dirty || save.isPending}
                className="rounded-full bg-beige text-cream px-6 text-[10px] font-medium"
              >
                {save.isPending ? (
                  <>
                    <VocifySpinner size={12} />
                    {t.product.noteSaving}
                  </>
                ) : (
                  t.product.saveButton
                )}
              </Button>
            </div>
          </>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
};
