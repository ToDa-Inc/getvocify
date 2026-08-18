import { useState } from "react";
import { Button } from "@/components/ui/button";
import { crmApi } from "@/lib/api/crm";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

interface SalesforceConnectionProps {
  onConnected: () => void;
}

export const SalesforceConnection = ({ onConnected }: SalesforceConnectionProps) => {
  const [isLoading, setIsLoading] = useState(false);

  const handleConnect = async () => {
    setIsLoading(true);
    try {
      const { redirect_url } = await crmApi.getSalesforceAuthorizeUrl();
      window.location.href = redirect_url;
    } catch (error: any) {
      setIsLoading(false);
      const msg = error?.data?.detail ?? error.message ?? "Failed to connect Salesforce";
      toast.error(msg);
    }
  };

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground leading-relaxed">
        Connect your Salesforce org via OAuth. You will authorize API access for opportunities, accounts, and contacts.
      </p>
      <Button
        onClick={handleConnect}
        disabled={isLoading}
        className="w-full bg-beige text-cream hover:bg-beige-dark rounded-lg text-sm font-medium h-11"
      >
        {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
        Connect with Salesforce
      </Button>
    </div>
  );
};
