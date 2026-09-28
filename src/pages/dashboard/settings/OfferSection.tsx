import { ProductOfferSettings } from "@/components/dashboard/settings/ProductOfferSettings";
import { CallbackDaysSettings } from "@/components/dashboard/settings/CallbackDaysSettings";
import { FollowupCadenceSettings } from "@/components/dashboard/settings/FollowupCadenceSettings";
import { SalesStrategySettings } from "@/components/dashboard/settings/SalesStrategySettings";
import { useAuth } from "@/features/auth";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const OfferSection = () => {
  const { user } = useAuth();
  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";
  const salesStrategyEnabled = Boolean(user?.company?.features?.includes("FOLLOWUP_BY_FLOW_ENABLED"));
  const leadTiersEnabled = Boolean(user?.company?.features?.includes("HOY_LEAD_TIERS_ENABLED"));
  // Lista 4 (E8): the cadence is what brings a contact back to the SDR's Seguimiento.
  const sdrSectionsEnabled = Boolean(user?.company?.features?.includes("HOY_SDR_SECTIONS_ENABLED"));

  return (
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8 space-y-6`}>
      <ProductOfferSettings readOnly={!canManage} />
      {salesStrategyEnabled && <SalesStrategySettings readOnly={!canManage} />}
      {leadTiersEnabled && <CallbackDaysSettings readOnly={!canManage} />}
      {sdrSectionsEnabled && <FollowupCadenceSettings readOnly={!canManage} />}
    </div>
  );
};

export default OfferSection;
