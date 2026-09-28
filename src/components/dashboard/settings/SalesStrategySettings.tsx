import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { companyApi, companyKeys } from "@/features/company/api";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/**
 * D10: the Head of Sales's sales strategy, used as context in follow-up, briefs and Ask.
 * Rendered only while FOLLOWUP_BY_FLOW_ENABLED (see OfferSection.tsx); read-only for members.
 */
export const SalesStrategySettings = ({ readOnly = false }: { readOnly?: boolean }) => {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const { data: company } = useQuery({ queryKey: companyKeys.detail(), queryFn: () => companyApi.get() });
  const [value, setValue] = useState(company?.salesStrategy ?? "");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setValue(company?.salesStrategy ?? "");
  }, [company?.salesStrategy]);

  const handleSave = async () => {
    try {
      setIsSaving(true);
      const updated = await companyApi.update({ salesStrategy: value });
      queryClient.setQueryData(companyKeys.detail(), updated);
      toast.success(t.product.salesStrategySavedToast);
    } catch {
      toast.error(t.product.salesStrategySaveFailedToast);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-4 border-t border-border/60 pt-5">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>{t.product.salesStrategyTitle}</h3>
        <p className="text-xs text-muted-foreground mt-1">{t.product.salesStrategyHelper}</p>
      </div>
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={6}
        maxLength={8000}
        readOnly={readOnly}
        disabled={readOnly}
        className="text-sm rounded-2xl"
        placeholder={t.product.salesStrategyPlaceholder}
      />
      {!readOnly && (
        <div className="flex justify-end">
          <Button
            onClick={handleSave}
            disabled={isSaving}
            className="rounded-full bg-beige text-cream px-6 text-[10px] font-medium"
          >
            {isSaving ? (
              <>
                <VocifySpinner size={12} />
                {t.product.salesStrategySaving}
              </>
            ) : (
              t.product.salesStrategySaveButton
            )}
          </Button>
        </div>
      )}
    </div>
  );
};
