import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi } from "@/lib/api/crm";
import { toast } from "sonner";
import { Loader2, Key } from "lucide-react";

interface HubSpotConnectionProps {
  onConnected: () => void;
}

export const HubSpotConnection = ({ onConnected }: HubSpotConnectionProps) => {
  const [accessToken, setAccessToken] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessToken.trim()) {
      toast.error("Please enter a Private App Access Token");
      return;
    }

    setIsLoading(true);
    try {
      await crmApi.connectHubSpot(accessToken);
      toast.success("HubSpot connected successfully!");
      onConnected();
    } catch (error: any) {
      toast.error(error.message || "Failed to connect HubSpot");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <label className={THEME_TOKENS.typography.capsLabel}>
          Private App Access Token
        </label>
        <div className="relative">
          <Input
            type="password"
            placeholder="pat-na1-..."
            value={accessToken}
            onChange={(e) => setAccessToken(e.target.value)}
            className="bg-secondary/5 border-border/40 rounded-full pl-12 pr-6 h-12 font-bold"
          />
          <Key className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40" />
        </div>
        <p className="text-[10px] text-muted-foreground mt-2 leading-relaxed px-4">
          Create a Private App in HubSpot with <code className="text-beige">crm.objects.deals</code>, <code className="text-beige">crm.objects.contacts</code>, and <code className="text-beige">crm.schemas.deals</code> scopes.
        </p>
      </div>

      <Button
        onClick={handleConnect}
        disabled={isLoading}
        className="w-full bg-beige text-cream hover:bg-beige-dark rounded-full text-[10px] font-black uppercase tracking-widest shadow-medium h-12"
      >
        {isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin mr-2" />
        ) : null}
        Verify & Connect
      </Button>
    </div>
  );
};

