import { ProductOfferSettings } from "@/components/dashboard/settings/ProductOfferSettings";
import { CallbackDaysSettings } from "@/components/dashboard/settings/CallbackDaysSettings";
import { SalesStrategySettings } from "@/components/dashboard/settings/SalesStrategySettings";
import { useAuth } from "@/features/auth";
import { SettingsSection } from "@/components/ui/settings-card";

const OfferSection = () => {
  const { user } = useAuth();
  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";
  const salesStrategyEnabled = Boolean(user?.company?.features?.includes("FOLLOWUP_BY_FLOW_ENABLED"));
  const leadTiersEnabled = Boolean(user?.company?.features?.includes("HOY_LEAD_TIERS_ENABLED"));

  return (
    <div className="mx-auto max-w-[680px] space-y-8">
      <SettingsSection>
        <div className="py-5">
          <ProductOfferSettings readOnly={!canManage} />
        </div>
      </SettingsSection>
      {salesStrategyEnabled && (
        <SettingsSection>
          <div className="py-5">
            <SalesStrategySettings readOnly={!canManage} />
          </div>
        </SettingsSection>
      )}
      {leadTiersEnabled && (
        <SettingsSection>
          <div className="py-5">
            <CallbackDaysSettings readOnly={!canManage} />
          </div>
        </SettingsSection>
      )}
    </div>
  );
};

export default OfferSection;
