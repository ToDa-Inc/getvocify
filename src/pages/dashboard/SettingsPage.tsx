import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
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
        // Connection ≠ saved configuration: use connections list, not config 404.
        const { connections } = await crmApi.listConnections();
        const hubspotConnected = (connections || []).some(
          (c) => c.provider === "hubspot" && c.status === "connected",
        );
        setIsHubSpotConnected(hubspotConnected);
      } catch (error) {
        console.error("Failed to check connection", error);
        setIsHubSpotConnected(false);
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

      {isHubSpotConnected ? (
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
      ) : (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 border-2 border-border/30`}>
          <h2 className={THEME_TOKENS.typography.sectionTitle}>CRM configuration</h2>
          <p className="text-sm text-muted-foreground mt-2 mb-4">
            Connect HubSpot in Integrations to manage pipelines and field allowlists here.
          </p>
          <Link
            to="/dashboard/integrations"
            className="inline-flex items-center justify-center rounded-full bg-beige text-cream px-6 py-2 text-[10px] font-black uppercase tracking-widest"
          >
            Open Integrations
          </Link>
        </div>
      )}

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-10 border-2 border-beige/10 bg-gradient-to-br from-white to-beige/5`}>
        <UserGlossary />
      </div>
    </div>
  );
};

export default SettingsPage;
