import { useState } from "react";
import { Button } from "@/components/ui/button";
import { crmApi } from "@/lib/api/crm";
import { errorDetail } from "@/shared/lib";
import { toast } from "sonner";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { HUBSPOT_CONNECT_EMAIL_HINT } from "@/lib/identity-hints";

interface HubSpotConnectionProps {
  onConnected: () => void;
}

export const HubSpotConnection = ({ onConnected }: HubSpotConnectionProps) => {
  const [isLoading, setIsLoading] = useState(false);

  const handleConnect = async () => {
    setIsLoading(true);
    try {
      const { redirect_url } = await crmApi.getHubSpotAuthorizeUrl();
      window.location.href = redirect_url;
    } catch (error: unknown) {
      setIsLoading(false);
      toast.error(errorDetail(error, "Failed to connect HubSpot"));
    }
  };

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground leading-relaxed">
        Connect your HubSpot account securely via OAuth. You'll be redirected to HubSpot to authorize access to your deals, contacts, companies, and notes.
      </p>
      <p className="text-xs text-muted-foreground leading-relaxed">
        {HUBSPOT_CONNECT_EMAIL_HINT}
      </p>

      <Button
        onClick={handleConnect}
        disabled={isLoading}
        className="w-full bg-beige text-cream hover:bg-beige-dark rounded-lg text-sm font-medium h-11"
      >
        {isLoading ? <VocifySpinner size={12} /> : null}
        Connect with HubSpot
      </Button>
    </div>
  );
};

