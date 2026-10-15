import { ProductOfferSettings } from "@/components/dashboard/settings/ProductOfferSettings";
import { SettingsSection } from "@/components/ui/settings-card";
import { useAuth } from "@/features/auth";

const OfferSection = () => {
  const { user } = useAuth();
  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";

  return (
    <div className="mx-auto max-w-[680px]">
      <SettingsSection>
        <div className="py-5">
          <ProductOfferSettings readOnly={!canManage} />
        </div>
      </SettingsSection>
    </div>
  );
};

export default OfferSection;
