import { useAuth } from "@/features/auth";
import type { CRMConfiguration } from "@/lib/api/crm";
import { useLanguage } from "@/lib/i18n";
import { productText } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type DealCreationRule = NonNullable<CRMConfiguration["deal_creation_rule"]>;

const RULES: DealCreationRule[] = ["always", "meeting_booked", "follow_up_or_meeting", "never"];

/**
 * Lista 4 E11 (AFTER_CALL_FLOW_ENABLED): when Vocify creates the deal for a contact without one.
 * Saved with the rest of the CRM configuration (Head of Sales only; read-only for members).
 * HubSpot and Pipedrive only: a Salesforce sync always needs an opportunity.
 */
export const DealCreationRuleField = ({
  value,
  disabled = false,
  onChange,
}: {
  value: CRMConfiguration["deal_creation_rule"];
  disabled?: boolean;
  onChange: (rule: DealCreationRule) => void;
}) => {
  const { t } = useLanguage();
  const { user } = useAuth();
  if (!user?.company?.features?.includes("AFTER_CALL_FLOW_ENABLED")) return null;
  const copy = t.product;
  return (
    <div className="space-y-3">
      <h4 className={THEME_TOKENS.typography.capsLabel}>{copy.dealCreationRuleLabel}</h4>
      <Select
        value={value ?? "always"}
        disabled={disabled}
        onValueChange={(rule) => onChange(rule as DealCreationRule)}
      >
        <SelectTrigger className="w-full" aria-label={copy.dealCreationRuleLabel}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {RULES.map((rule) => (
            <SelectItem key={rule} value={rule}>
              {productText(`dealCreationRule_${rule}`, copy)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-xs text-muted-foreground">{copy.dealCreationRuleHelper}</p>
    </div>
  );
};
