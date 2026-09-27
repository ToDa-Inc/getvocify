import { ProductOfferSettings } from "@/components/dashboard/settings/ProductOfferSettings";
import { SalesStrategySettings } from "@/components/dashboard/settings/SalesStrategySettings";
import { useAuth } from "@/features/auth";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const OfferSection = () => {
  const { user } = useAuth();
  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";
  const salesStrategyEnabled = Boolean(user?.company?.features?.includes("FOLLOWUP_BY_FLOW_ENABLED"));

  return (
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8 space-y-6`}>
      <ProductOfferSettings readOnly={!canManage} />
      {salesStrategyEnabled && <SalesStrategySettings readOnly={!canManage} />}
    </div>
  );
};

export default OfferSection;
