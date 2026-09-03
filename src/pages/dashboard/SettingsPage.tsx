import { useState, useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { VocifyLoader } from "@/components/ui/vocify-loader";
import { HubSpotConfiguration } from "@/components/dashboard/hubspot/HubSpotConfiguration";
import { UserGlossary } from "@/components/dashboard/glossary/UserGlossary";
import { ProductOfferSettings } from "@/components/dashboard/settings/ProductOfferSettings";
import { TranscriptionLanguageSettings } from "@/components/dashboard/settings/TranscriptionLanguageSettings";
import { CallerIdSettings } from "@/components/dashboard/settings/CallerIdSettings";
import { crmApi } from "@/lib/api/crm";

const SettingsPage = () => {
  const [isHubSpotConnected, setIsHubSpotConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const location = useLocation();

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

  useEffect(() => {
    if (isLoading || location.hash !== "#caller-id") return;
    const node = document.getElementById("caller-id");
    if (!node) return;
    const scroll = () =>
      node.scrollIntoView({ behavior: "smooth", block: "start" });
    scroll();
    const id = window.setTimeout(scroll, 450);
    return () => window.clearTimeout(id);
  }, [isLoading, location.hash]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px]">
        <VocifyLoader size="lg" label="Loading Settings..." />
      </div>
    );
  }

  return (
    <div className={`max-w-2xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Account <span className={THEME_TOKENS.typography.accentTitle}>Settings</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>Manage field mapping, call languages, caller ID, offer context, and glossary.</p>
      </div>

      {isHubSpotConnected ? (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
          <div className="flex items-center gap-4 mb-10">
            <div className="w-12 h-12 rounded-2xl bg-beige/10 flex items-center justify-center">
              <ShieldCheck className="h-6 w-6 text-beige" />
            </div>
            <div>
              <h2 className={THEME_TOKENS.typography.sectionTitle}>HubSpot Configuration</h2>
              <p className="text-xs text-muted-foreground mt-1">Choose which HubSpot fields AI may fill from a call, and how each one is treated.</p>
            </div>
          </div>

          <HubSpotConfiguration />
        </div>
      ) : (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
          <h2 className={THEME_TOKENS.typography.sectionTitle}>CRM configuration</h2>
          <p className="text-sm text-muted-foreground mt-2 mb-4">
            Connect HubSpot in Integrations to manage pipelines and field allowlists here.
          </p>
          <Link
            to="/dashboard/integrations"
            className="inline-flex items-center justify-center rounded-lg bg-beige text-cream px-5 py-2 text-sm font-medium"
          >
            Open Integrations
          </Link>
        </div>
      )}

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
        <TranscriptionLanguageSettings />
      </div>

      <div id="caller-id" className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} scroll-mt-24 p-8`}>
        <CallerIdSettings />
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
        <ProductOfferSettings />
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
        <UserGlossary />
      </div>
    </div>
  );
};

export default SettingsPage;
