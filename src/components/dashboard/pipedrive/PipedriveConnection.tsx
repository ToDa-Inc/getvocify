import { useState } from "react";
import { Button } from "@/components/ui/button";
import { crmApi } from "@/lib/api/crm";
import { toast } from "sonner";
import { VocifySpinner } from "@/components/ui/vocify-loader";

interface PipedriveConnectionProps {
  onConnected: () => void;
}

export const PipedriveConnection = ({ onConnected }: PipedriveConnectionProps) => {
  const [isLoading, setIsLoading] = useState(false);

  const handleConnect = async () => {
    setIsLoading(true);
    try {
      const { redirect_url } = await crmApi.getPipedriveAuthorizeUrl();
      window.location.href = redirect_url;
    } catch (error: any) {
      setIsLoading(false);
      const msg = error?.data?.detail ?? error.message ?? "Failed to connect Pipedrive";
      toast.error(msg);
    }
  };

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground leading-relaxed">
        Connect your Pipedrive account via OAuth. You will authorize API access for deals, people, organizations, notes, and activities.
      </p>
      <Button
        onClick={handleConnect}
        disabled={isLoading}
        className="w-full bg-beige text-cream hover:bg-beige-dark rounded-lg text-sm font-medium h-11"
      >
        {isLoading ? <VocifySpinner size={12} /> : null}
        Connect with Pipedrive
      </Button>
    </div>
  );
};
