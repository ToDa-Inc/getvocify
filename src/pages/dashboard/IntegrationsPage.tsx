import { useState, useEffect, useCallback } from "react";
import { Check, X, RefreshCw, Loader2, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { HubSpotConnection } from "@/components/dashboard/hubspot/HubSpotConnection";
import { HubSpotConfiguration } from "@/components/dashboard/hubspot/HubSpotConfiguration";
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
  const [items, setItems] = useState(initialIntegrations);
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [selectedIntegrationId, setSelectedIntegrationId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchConnections = useCallback(async () => {
    try {
      const config = await crmApi.getConfiguration();
      
      setItems(prevItems => prevItems.map(item => {
        if (item.id === "hubspot" && config) {
          return { 
            ...item, 
            connected: true, 
            lastSync: "Active",
            details: {
              portal: config.default_pipeline_name,
              permissions: ["Deals", "Contacts", "Companies"]
            }
          };
        }
        return item;
      }));
    } catch (error) {
      console.error("Failed to check connections", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  const handleConnectClick = (id: string) => {
    if (id !== "hubspot") {
      toast.info(`${initialIntegrations.find(i => i.id === id)?.name} integration coming soon!`);
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

  const handleDisconnect = (id: string) => {
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

      <div className="grid sm:grid-cols-2 gap-8 mt-12">
        {items.map((integration) => (
          <div
            key={integration.id}
            className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-10 ${THEME_TOKENS.cards.hover} group`}
          >
            <div className="flex items-start justify-between mb-8">
              <div className="flex items-center gap-6">
                <div className="w-16 h-16 rounded-2xl bg-secondary/5 flex items-center justify-center p-4 group-hover:scale-110 transition-transform">
                  <img src={integration.logo} alt={integration.name} className="w-full h-full object-contain grayscale group-hover:grayscale-0 transition-all duration-500" />
                </div>
                <div>
                  <h3 className="font-bold text-foreground text-xl">{integration.name}</h3>
                  {integration.connected ? (
                    <span className="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-success">
                      <span className="w-1.5 h-1.5 rounded-full bg-success shadow-[0_0_8px_rgba(34,197,94,0.4)]" />
                      Connected
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
        ))}
      </div>

      <Dialog open={isConnectModalOpen} onOpenChange={setIsConnectModalOpen}>
        <DialogContent className={`${THEME_TOKENS.radius.container} border-none p-10 bg-white shadow-large max-w-lg`}>
          <DialogHeader className="mb-8">
            <DialogTitle className="text-2xl font-black tracking-tight flex items-center gap-3">
              Connect <span className="text-beige">HubSpot</span>
            </DialogTitle>
            <DialogDescription className="text-sm leading-relaxed">
              Authenticate using a Private App Access Token to enable secure, direct access to your CRM objects.
            </DialogDescription>
          </DialogHeader>
          
          <HubSpotConnection onConnected={handleConnected} />
        </DialogContent>
      </Dialog>

      <Dialog open={isConfigModalOpen} onOpenChange={setIsConfigModalOpen}>
        <DialogContent className={`${THEME_TOKENS.radius.container} border-none p-10 bg-white shadow-large max-w-2xl max-h-[90vh] overflow-y-auto`}>
          <DialogHeader className="mb-8">
            <DialogTitle className="text-2xl font-black tracking-tight flex items-center gap-3">
              Configure <span className="text-beige">{items.find(i => i.id === selectedIntegrationId)?.name}</span>
            </DialogTitle>
            <DialogDescription className="text-sm leading-relaxed">
              Set up your default pipeline and select which fields the AI can update.
            </DialogDescription>
          </DialogHeader>
          
          <HubSpotConfiguration onSaved={() => {
            setIsConfigModalOpen(false);
            fetchConnections();
          }} />
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default IntegrationsPage;
