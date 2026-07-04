import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Check, X, Loader2, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { HubSpotConnection } from "@/components/dashboard/hubspot/HubSpotConnection";
import { HubSpotConfiguration } from "@/components/dashboard/hubspot/HubSpotConfiguration";
import { SalesforceConnection } from "@/components/dashboard/salesforce/SalesforceConnection";
import { SalesforceConfiguration } from "@/components/dashboard/salesforce/SalesforceConfiguration";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { crmApi } from "@/lib/api/crm";

interface Integration {
  id: string;
  name: string;
  description: string;
  logo: string;
  connected: boolean;
  lastSync?: string;
  details?: {
    portal?: string;
    email?: string;
    permissions?: string[];
  };
}

const initialIntegrations: Integration[] = [
  {
    id: "hubspot",
    name: "HubSpot",
    description: "Update deals, contacts, and activities",
    logo: "https://cdn.worldvectorlogo.com/logos/hubspot.svg",
    connected: false,
  },
  {
    id: "salesforce",
    name: "Salesforce",
    description: "Sync opportunities and contacts",
    logo: "https://cdn.worldvectorlogo.com/logos/salesforce-2.svg",
    connected: false,
  },
  {
    id: "pipedrive",
    name: "Pipedrive",
    description: "Manage deals and pipeline",
    logo: "https://cdn.worldvectorlogo.com/logos/pipedrive.svg",
    connected: false,
  },
  {
    id: "slack",
    name: "Slack",
    description: "Send memos directly to channels",
    logo: "https://cdn.worldvectorlogo.com/logos/slack-new-logo.svg",
    connected: false,
  },
];

const IntegrationsPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState(initialIntegrations);
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [selectedIntegrationId, setSelectedIntegrationId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [primaryConnectionId, setPrimaryConnectionId] = useState<string | null>(null);
  const [connectionRows, setConnectionRows] = useState<{ id: string; provider: string }[]>([]);

  const fetchConnections = useCallback(async () => {
    try {
      const { connections } = await crmApi.listConnections();
      const connected = (connections || []).filter((c) => c.status === "connected");
      setConnectionRows(connected.map((c) => ({ id: c.id, provider: c.provider })));

      let prefs: { primary_crm_connection_id: string | null } = { primary_crm_connection_id: null };
      try {
        prefs = await crmApi.getCrmPreferences();
      } catch {
        /* ignore */
      }
      setPrimaryConnectionId(prefs.primary_crm_connection_id);

      let hubConfig = null as Awaited<ReturnType<typeof crmApi.getConfiguration>>;
      let sfConfig = null as Awaited<ReturnType<typeof crmApi.getSalesforceConfiguration>>;
      const hasHub = connected.some((c) => c.provider === "hubspot");
      const hasSf = connected.some((c) => c.provider === "salesforce");
      if (hasHub) {
        try {
          hubConfig = await crmApi.getConfiguration();
        } catch {
          hubConfig = null;
        }
      }
      if (hasSf) {
        try {
          sfConfig = await crmApi.getSalesforceConfiguration();
        } catch {
          sfConfig = null;
        }
      }

      setItems((prevItems) =>
        prevItems.map((item) => {
          if (item.id === "hubspot" && hasHub) {
            return {
              ...item,
              connected: true,
              lastSync: "Active",
              details: {
                portal: hubConfig?.default_pipeline_name || hubConfig?.default_stage_name || "HubSpot",
                permissions: ["Deals", "Contacts", "Companies"],
              },
            };
          }
          if (item.id === "salesforce" && hasSf) {
            return {
              ...item,
              connected: true,
              lastSync: "Active",
              details: {
                portal: sfConfig?.default_stage_name || "Salesforce",
                permissions: ["Opportunities", "Accounts", "Contacts"],
              },
            };
          }
          if (item.id === "hubspot" || item.id === "salesforce") {
            return { ...item, connected: false, lastSync: undefined, details: undefined };
          }
          return item;
        }),
      );
    } catch (error) {
      console.error("Failed to check connections", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  useEffect(() => {
    const hubspot = searchParams.get("hubspot");
    const salesforce = searchParams.get("salesforce");
    const error = searchParams.get("error");
    if (hubspot === "connected") {
      toast.success("HubSpot connected successfully!");
      setSearchParams({}, { replace: true });
      fetchConnections();
      setSelectedIntegrationId("hubspot");
      setTimeout(() => setIsConfigModalOpen(true), 300);
    } else if (salesforce === "connected") {
      toast.success("Salesforce connected successfully!");
      setSearchParams({}, { replace: true });
      fetchConnections();
      setSelectedIntegrationId("salesforce");
      setTimeout(() => setIsConfigModalOpen(true), 300);
    } else if (hubspot === "error" || salesforce === "error" || error) {
      const errDesc = searchParams.get("error_description");
      const decoded = errDesc ? decodeURIComponent(errDesc.replace(/\+/g, " ")) : "";
      let msg: string;
      if (error === "invalid_state") {
        msg = "Session expired. Please try again.";
      } else if (salesforce === "error") {
        if (error === "OAUTH_EC_APP_NOT_FOUND" || decoded.toLowerCase().includes("not installed")) {
          msg =
            "Salesforce rejected login: this External Client App is not installed in the org you signed into. Create or enable Vocify in that org, or log in to the same org where you built the app (same Client ID).";
        } else if (decoded) {
          msg = `Salesforce: ${decoded}`;
        } else if (error && error !== "error") {
          msg = `Salesforce: ${error}`;
        } else {
          msg = "Failed to connect Salesforce.";
        }
      } else {
        msg = "Failed to connect HubSpot.";
      }
      toast.error(msg, { duration: 12_000 });
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams, fetchConnections]);

  const handleConnectClick = (id: string) => {
    if (id !== "hubspot" && id !== "salesforce") {
      toast.info(`${initialIntegrations.find((i) => i.id === id)?.name} integration coming soon!`);
      return;
    }
    setSelectedIntegrationId(id);
    setIsConnectModalOpen(true);
  };

  const handleConnected = () => {
    fetchConnections();
    setIsConnectModalOpen(false);
    // Automatically open configuration after connection
    setTimeout(() => setIsConfigModalOpen(true), 500);
  };

  const handleConfigureClick = (id: string) => {
    setSelectedIntegrationId(id);
    setIsConfigModalOpen(true);
  };

  const handleDisconnect = async (id: string) => {
    try {
      if (id === "hubspot") await crmApi.disconnectHubSpot();
      else if (id === "salesforce") await crmApi.disconnectSalesforce();
      else return;
    } catch {
      toast.error("Failed to disconnect");
      return;
    }
    setItems(prevItems => prevItems.map(item => 
      item.id === id ? { ...item, connected: false, lastSync: undefined, details: undefined } : item
    ));
    toast.success(`Disconnected from ${items.find(i => i.id === id)?.name}`);
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
        <Loader2 className="h-10 w-10 animate-spin text-beige" />
        <p className={THEME_TOKENS.typography.capsLabel}>Checking Connections...</p>
      </div>
    );
  }

  return (
    <div className={`max-w-4xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          CRM <span className={THEME_TOKENS.typography.accentTitle}>Connections</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>
          Seamlessly sync your voice memos with your existing stack.
        </p>
      </div>

      {connectionRows.length > 1 && (
        <div className="mt-8 p-6 rounded-3xl border border-border/30 bg-secondary/5">
          <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-3">
            Primary CRM for voice memo sync
          </p>
          <div className="flex flex-wrap gap-4">
            {connectionRows.map((c) => (
              <label key={c.id} className="flex items-center gap-2 cursor-pointer text-sm font-medium">
                <input
                  type="radio"
                  name="primary-crm"
                  checked={primaryConnectionId === c.id}
                  onChange={async () => {
                    try {
                      await crmApi.setPrimaryCrmConnection(c.id);
                      setPrimaryConnectionId(c.id);
                      toast.success("Primary CRM updated");
                    } catch {
                      toast.error("Could not update primary CRM");
                    }
                  }}
                />
                {c.provider === "hubspot" ? "HubSpot" : c.provider === "salesforce" ? "Salesforce" : c.provider}
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-8 mt-12">
        {items.map((integration) => {
          const isActiveCrm = integration.id === "hubspot" || integration.id === "salesforce";
          return (
          <div
            key={integration.id}
            className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-10 group ${!isActiveCrm ? "opacity-60 grayscale" : THEME_TOKENS.cards.hover}`}
          >
            <div className="flex items-start justify-between mb-8">
              <div className="flex items-center gap-6">
                  <div className={`w-16 h-16 rounded-2xl bg-secondary/5 flex items-center justify-center p-4 transition-transform ${isActiveCrm ? "group-hover:scale-110" : ""}`}>
                  <img src={integration.logo} alt={integration.name} className={`w-full h-full object-contain transition-all duration-500 ${isActiveCrm ? "grayscale group-hover:grayscale-0" : "grayscale"}`} />
                </div>
                <div>
                  <h3 className="font-bold text-foreground text-xl">{integration.name}</h3>
                  {integration.connected ? (
                    <span className="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-success">
                      <span className="w-1.5 h-1.5 rounded-full bg-success shadow-[0_0_8px_rgba(34,197,94,0.4)]" />
                      Connected
                      {connectionRows.length > 1 &&
                        primaryConnectionId &&
                        connectionRows.find((c) => c.provider === integration.id)?.id === primaryConnectionId && (
                          <span className="text-beige normal-case ml-1">(primary)</span>
                        )}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-muted-foreground/30">
                      Available
                    </span>
                  )}
                </div>
              </div>
            </div>

            <p className="text-sm text-muted-foreground mb-8 leading-relaxed font-medium">{integration.description}</p>

            {integration.connected && (
              <div className={`rounded-3xl p-6 mb-8 border transition-all ${
                integration.details?.portal 
                  ? 'bg-secondary/5 border-border/20' 
                  : 'bg-beige/5 border-beige/20 animate-pulse'
              }`}>
                <div className="flex justify-between items-center">
                  <div className="space-y-1">
                    <p className={`font-bold text-sm ${integration.details?.portal ? 'text-foreground' : 'text-beige'}`}>
                      {integration.details?.portal || "Pending Configuration"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {integration.details?.portal 
                        ? (integration.details?.email || "Automatic background sync") 
                        : "Click configure to set up your pipeline"}
                    </p>
                  </div>
                  {integration.details?.portal && (
                    <div className="flex flex-wrap gap-2 justify-end">
                      {(integration.details?.permissions || ["Deals", "Sync"]).map((perm) => (
                        <span key={perm} className="inline-flex items-center gap-1 text-[8px] font-black uppercase tracking-widest bg-success/10 text-success px-2 py-1 rounded-full border border-success/20">
                          <Check className="h-2.5 w-2.5" />
                          {perm}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="flex items-center gap-4">
              {integration.connected ? (
                <>
                  <Button 
                    size="lg"
                    variant={integration.details?.portal ? "default" : "hero"}
                    className={`flex-1 rounded-full text-[10px] font-black uppercase tracking-widest shadow-medium h-12 transition-all ${
                      integration.details?.portal 
                        ? 'bg-beige text-cream hover:bg-beige-dark' 
                        : 'bg-beige text-cream hover:bg-beige-dark scale-[1.05] shadow-large'
                    }`}
                    onClick={() => handleConfigureClick(integration.id)}
                  >
                    <Settings2 className="h-4 w-4 mr-2" />
                    {integration.details?.portal ? "Configure" : "Set Up Pipeline"}
                  </Button>
                  <Button 
                    variant="outline" 
                    size="icon" 
                    className="w-12 h-12 rounded-full border-border/50 hover:bg-destructive/5 hover:text-destructive hover:border-destructive/20"
                    onClick={() => handleDisconnect(integration.id)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </>
              ) : (
                <Button 
                  size="lg" 
                  className="w-full bg-beige text-cream hover:bg-beige-dark rounded-full text-[10px] font-black uppercase tracking-widest shadow-medium hover:scale-[1.02] transition-all h-12"
                  onClick={() => handleConnectClick(integration.id)}
                >
                  Connect {integration.name}
                </Button>
              )}
            </div>

            {integration.lastSync && (
              <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground/20 mt-6 text-center">
                Last activity: {integration.lastSync}
              </p>
            )}
          </div>
        );})}
      </div>

      <Dialog open={isConnectModalOpen} onOpenChange={setIsConnectModalOpen}>
        <DialogContent className={`${THEME_TOKENS.radius.container} border-none p-10 bg-white shadow-large max-w-lg`}>
          <DialogHeader className="mb-8">
            <DialogTitle className="text-2xl font-black tracking-tight flex items-center gap-3">
              Connect{" "}
              <span className="text-beige">
                {selectedIntegrationId === "salesforce" ? "Salesforce" : "HubSpot"}
              </span>
            </DialogTitle>
            <DialogDescription className="text-sm leading-relaxed">
              {selectedIntegrationId === "salesforce"
                ? "You will be redirected to Salesforce to authorize API access."
                : "Connect securely via OAuth. You'll be redirected to HubSpot to authorize access."}
            </DialogDescription>
          </DialogHeader>

          {selectedIntegrationId === "salesforce" ? (
            <SalesforceConnection onConnected={handleConnected} />
          ) : (
            <HubSpotConnection onConnected={handleConnected} />
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={isConfigModalOpen} onOpenChange={setIsConfigModalOpen}>
        <DialogContent className={`${THEME_TOKENS.radius.container} border-none p-10 bg-white shadow-large max-w-2xl max-h-[90vh] overflow-y-auto`}>
          <DialogHeader className="mb-8">
            <DialogTitle className="text-2xl font-black tracking-tight flex items-center gap-3">
              Configure <span className="text-beige">{items.find((i) => i.id === selectedIntegrationId)?.name}</span>
            </DialogTitle>
            <DialogDescription className="text-sm leading-relaxed">
              Set up defaults and select which fields the AI can update in your CRM.
            </DialogDescription>
          </DialogHeader>

          {selectedIntegrationId === "salesforce" ? (
            <SalesforceConfiguration
              onSaved={() => {
                setIsConfigModalOpen(false);
                fetchConnections();
              }}
            />
          ) : (
            <HubSpotConfiguration
              onSaved={() => {
                setIsConfigModalOpen(false);
                fetchConnections();
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default IntegrationsPage;
