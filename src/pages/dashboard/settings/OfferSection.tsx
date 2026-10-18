import { Navigate } from "react-router-dom";
import { ProductOfferSettings } from "@/components/dashboard/settings/ProductOfferSettings";
import { SettingsSection } from "@/components/ui/settings-card";
import { useAuth } from "@/features/auth";

const OfferSection = () => {
  const { user } = useAuth();
  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";
  // With the editable sales process the product and offer are filled in from "Vuestra empresa", in Playbook.
  if (user?.company?.features?.includes("SALES_PROCESS_ENABLED")) return <Navigate to="/dashboard/playbook" replace />;

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
