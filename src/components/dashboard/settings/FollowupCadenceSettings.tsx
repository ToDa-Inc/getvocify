import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { companyApi, companyKeys } from "@/features/company/api";
import {
  CADENCE_MAX_DAYS,
  CADENCE_MIN_DAYS,
  CADENCE_STOPPERS,
  cadenceInputs,
  cadenceOverrides,
  validDays,
} from "@/lib/followup-cadence";
import { useLanguage } from "@/lib/i18n";
import { productText } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/**
 * Lista 4 (E8): how long a hot contact waits before coming back to Seguimiento, per stopper
 * (companies.followup_cadence). Rendered only while HOY_SDR_SECTIONS_ENABLED (see
 * OfferSection.tsx) - that is what the cadence drives; read-only for members.
 */
export const FollowupCadenceSettings = ({ readOnly = false }: { readOnly?: boolean }) => {
  const { t } = useLanguage();
  const copy = t.product;
  const queryClient = useQueryClient();
  const { data: company } = useQuery({ queryKey: companyKeys.detail(), queryFn: () => companyApi.get() });
  const defaults = company?.followupCadenceDefaults ?? null;
  const saved = useMemo(
    () => cadenceInputs(company?.followupCadence, defaults),
    [company?.followupCadence, defaults],
  );
  const [inputs, setInputs] = useState(saved);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => setInputs(saved), [saved]);

  if (!defaults) return null;
  const overrides = cadenceOverrides(inputs, defaults);

  const handleSave = async () => {
    if (!overrides) return;
    try {
      setIsSaving(true);
      const updated = await companyApi.update({ followupCadence: overrides });
      queryClient.setQueryData(companyKeys.detail(), updated);
      toast.success(copy.callbackDaysSavedToast);
    } catch {
      toast.error(copy.callbackDaysSaveFailedToast);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-3 border-t border-border/60 pt-5">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>{copy.followupCadenceTitle}</h3>
        <p className="text-xs text-muted-foreground mt-1">{copy.followupCadenceHelper}</p>
      </div>
      <ul className="grid gap-2 sm:grid-cols-2">
        {CADENCE_STOPPERS.map((stopper) => {
          const label = productText(`followupCadence_${stopper}`, copy);
          const value = inputs[stopper];
          return (
            <li key={stopper} className="flex items-center gap-3">
              <span className="min-w-0 flex-1 text-[13px] text-foreground">
                {label}
                <span className="ml-1.5 text-[11px] text-muted-foreground">
                  {copy.followupCadenceDefault.replace("{days}", String(defaults[stopper] ?? ""))}
                </span>
              </span>
              <Input
                type="number"
                inputMode="numeric"
                min={CADENCE_MIN_DAYS}
                max={CADENCE_MAX_DAYS}
                value={value}
                onChange={(event) => setInputs((prev) => ({ ...prev, [stopper]: event.target.value }))}
                readOnly={readOnly}
                disabled={readOnly}
                aria-label={label}
                aria-invalid={!validDays(value)}
                className="w-20 rounded-full text-sm"
              />
              <span className="text-[12px] text-muted-foreground">{copy.callbackDaysUnit}</span>
            </li>
          );
        })}
      </ul>
      {!readOnly && (
        <div className="flex justify-end">
          <Button
            onClick={handleSave}
            disabled={isSaving || !overrides}
            className="rounded-full bg-beige text-cream px-6 text-[10px] font-medium"
          >
            {copy.callbackDaysSaveButton}
          </Button>
        </div>
      )}
    </div>
  );
};
