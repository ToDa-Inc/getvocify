import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { companyApi, companyKeys } from "@/features/company/api";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

export const CALLBACK_DAYS_MIN = 1;
export const CALLBACK_DAYS_MAX = 30;

/**
 * T5: how many days after an unanswered call Hoy suggests calling back
 * (companies.callback_after_days, default 2). Rendered only while HOY_LEAD_TIERS_ENABLED
 * (see OfferSection.tsx); read-only for members.
 */
export const CallbackDaysSettings = ({ readOnly = false }: { readOnly?: boolean }) => {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const { data: company } = useQuery({ queryKey: companyKeys.detail(), queryFn: () => companyApi.get() });
  const [value, setValue] = useState(String(company?.callbackAfterDays ?? 2));
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setValue(String(company?.callbackAfterDays ?? 2));
  }, [company?.callbackAfterDays]);

  const days = Number(value);
  const valid = Number.isInteger(days) && days >= CALLBACK_DAYS_MIN && days <= CALLBACK_DAYS_MAX;

  const handleSave = async () => {
    if (!valid) return;
    try {
      setIsSaving(true);
      const updated = await companyApi.update({ callbackAfterDays: days });
      queryClient.setQueryData(companyKeys.detail(), updated);
      toast.success(t.product.callbackDaysSavedToast);
    } catch {
      toast.error(t.product.callbackDaysSaveFailedToast);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-3 border-t border-border/60 pt-5">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>{t.product.callbackDaysTitle}</h3>
        <p className="text-xs text-muted-foreground mt-1">{t.product.callbackDaysHelper}</p>
      </div>
      <div className="flex items-center gap-3">
        <Input
          type="number"
          inputMode="numeric"
          min={CALLBACK_DAYS_MIN}
          max={CALLBACK_DAYS_MAX}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          readOnly={readOnly}
          disabled={readOnly}
          aria-label={t.product.callbackDaysTitle}
          aria-invalid={!valid}
          className="w-24 rounded-full text-sm"
        />
        <span className="text-sm text-muted-foreground">{t.product.callbackDaysUnit}</span>
        {!readOnly && (
          <Button
            onClick={handleSave}
            disabled={isSaving || !valid}
            className="ml-auto rounded-full bg-beige text-cream px-6 text-[10px] font-medium"
          >
            {t.product.callbackDaysSaveButton}
          </Button>
        )}
      </div>
    </div>
  );
};
