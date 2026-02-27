import { useState, useEffect } from "react";
import { ShieldCheck, Loader2 } from "lucide-react";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { HubSpotConfiguration } from "@/components/dashboard/hubspot/HubSpotConfiguration";
import { UserGlossary } from "@/components/dashboard/glossary/UserGlossary";
import { crmApi } from "@/lib/api/crm";

const SettingsPage = () => {
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
        <p className={THEME_TOKENS.typography.body}>Manage integrations and glossary.</p>
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
    </div>
  );
};

export default SettingsPage;
