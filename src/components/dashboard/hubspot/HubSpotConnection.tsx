import { useState } from "react";
import { Button } from "@/components/ui/button";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi } from "@/lib/api/crm";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

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
    } catch (error: any) {
      setIsLoading(false);
      const msg = error?.data?.detail ?? error.message ?? "Failed to connect HubSpot";
      toast.error(msg);
    }
  };

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground leading-relaxed">
        Connect your HubSpot account securely via OAuth. You'll be redirected to HubSpot to authorize access to your deals, contacts, and companies.
      </p>

      <Button
        onClick={handleConnect}
        disabled={isLoading}
        className="w-full bg-beige text-cream hover:bg-beige-dark rounded-full text-[10px] font-black uppercase tracking-widest shadow-medium h-12"
      >
        {isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin mr-2" />
        ) : null}
        Connect with HubSpot
      </Button>
    </div>
  );
};

