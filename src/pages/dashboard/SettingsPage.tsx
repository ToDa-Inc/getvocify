import { useState, useEffect } from "react";
import { ShieldCheck, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { HubSpotConfiguration } from "@/components/dashboard/hubspot/HubSpotConfiguration";
import { UserGlossary } from "@/components/dashboard/glossary/UserGlossary";
import { crmApi } from "@/lib/api/crm";
import { useAuth } from "@/features/auth";
import { authApi, authKeys } from "@/features/auth/api";

const SettingsPage = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [autoApprove, setAutoApprove] = useState(true);
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [slackNotifications, setSlackNotifications] = useState(false);
  const [isHubSpotConnected, setIsHubSpotConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const checkConnection = async () => {
      try {
        const config = await crmApi.getConfiguration();
        setIsHubSpotConnected(!!config);
      } catch (error) {
        console.error("Failed to check connection", error);
      } finally {
        setIsLoading(false);
      }
    };
    checkConnection();
  }, []);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
        <Loader2 className="h-10 w-10 animate-spin text-beige" />
        <p className={THEME_TOKENS.typography.capsLabel}>Loading Settings...</p>
      </div>
    );
  }

  return (
    <div className={`max-w-2xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Account <span className={THEME_TOKENS.typography.accentTitle}>Settings</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>Manage integrations, glossary, and preferences.</p>
      </div>

      {/* HubSpot Configuration */}
      {isHubSpotConnected && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-10 border-2 border-beige/10`}>
          <div className="flex items-center gap-4 mb-10">
            <div className="w-12 h-12 rounded-2xl bg-beige/10 flex items-center justify-center">
              <ShieldCheck className="h-6 w-6 text-beige" />
            </div>
            <div>
              <h2 className={THEME_TOKENS.typography.sectionTitle}>HubSpot Configuration</h2>
              <p className="text-xs text-muted-foreground mt-1">Manage your pipeline and field mapping preferences.</p>
            </div>
          </div>
          
          <HubSpotConfiguration />
        </div>
      )}

      {/* AI Glossary / Custom Vocabulary */}
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-10 border-2 border-beige/10 bg-gradient-to-br from-white to-beige/5`}>
        <UserGlossary />
      </div>

      {/* Preferences */}
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
        <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-8`}>Preferences</h2>
        
        <div className="space-y-8">
          <div className="space-y-3">
            <label className={THEME_TOKENS.typography.capsLabel}>Default CRM</label>
            <select className="w-full h-12 px-6 rounded-full border border-border/40 bg-secondary/5 text-foreground appearance-none cursor-pointer font-bold focus:outline-none">
              <option>HubSpot</option>
              <option disabled>Salesforce (Coming Soon)</option>
              <option disabled>Pipedrive (Coming Soon)</option>
            </select>
          </div>

          <div className="flex items-center justify-between p-4 rounded-2xl bg-secondary/5 border border-border/20">
            <div>
              <p className="font-bold text-foreground">Auto-approve updates</p>
              <p className="text-xs text-muted-foreground mt-0.5 tracking-tight">Approve updates with 95%+ confidence</p>
            </div>
            <Switch checked={autoApprove} onCheckedChange={setAutoApprove} />
          </div>

          <div className="flex items-center justify-between p-4 rounded-2xl bg-secondary/5 border border-border/20">
            <div>
              <p className="font-bold text-foreground">Email notifications</p>
              <p className="text-xs text-muted-foreground mt-0.5 tracking-tight">Get notified when memos are processed</p>
            </div>
            <Switch checked={emailNotifications} onCheckedChange={setEmailNotifications} />
          </div>

          <div className="flex items-center justify-between p-4 rounded-2xl bg-secondary/5 border border-border/20">
            <div className="flex-1">
              <p className="font-bold text-foreground">Slack Integration</p>
              <p className="text-xs text-muted-foreground mt-0.5 tracking-tight">Send updates to your Slack channel</p>
            </div>
            <div className="flex items-center gap-4">
              {!slackNotifications && (
                <Button variant="outline" size="sm" className="rounded-full px-4 text-[10px] font-black uppercase tracking-widest border-border/50">
                  Connect
                </Button>
              )}
              <Switch checked={slackNotifications} onCheckedChange={setSlackNotifications} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;
