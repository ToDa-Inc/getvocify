import { useState } from "react";
import { Check, X, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

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

const integrations: Integration[] = [
  {
    id: "hubspot",
    name: "HubSpot",
    description: "Update deals, contacts, and activities",
    logo: "🟠",
    connected: true,
    lastSync: "2 hours ago",
    details: {
      portal: "Acme Corp",
      email: "john@acme.com",
      permissions: ["Deals", "Contacts", "Activities"],
    },
  },
  {
    id: "salesforce",
    name: "Salesforce",
    description: "Sync opportunities and contacts",
    logo: "☁️",
    connected: false,
  },
  {
    id: "pipedrive",
    name: "Pipedrive",
    description: "Manage deals and pipeline",
    logo: "🟢",
    connected: false,
  },
  {
    id: "gohighlevel",
    name: "GoHighLevel",
    description: "Update contacts and opportunities",
    logo: "🔵",
    connected: false,
  },
];

const IntegrationsPage = () => {
  const [items, setItems] = useState(integrations);

  const handleConnect = (id: string) => {
    setItems(items.map(item => 
      item.id === id ? { ...item, connected: true, lastSync: "Just now" } : item
    ));
    toast.success(`Connected to ${items.find(i => i.id === id)?.name}`);
  };

  const handleDisconnect = (id: string) => {
    setItems(items.map(item => 
      item.id === id ? { ...item, connected: false, lastSync: undefined, details: undefined } : item
    ));
    toast.success(`Disconnected from ${items.find(i => i.id === id)?.name}`);
  };

  const handleTestConnection = (id: string) => {
    toast.success("Connection test successful!");
  };

  return (
    <div className="max-w-4xl mx-auto animate-fade-in">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">CRM Connections</h1>
        <p className="text-muted-foreground">
          Connect your CRM to start updating deals with voice memos
        </p>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        {items.map((integration) => (
          <div
            key={integration.id}
            className="bg-card rounded-2xl shadow-soft p-6 hover:shadow-medium transition-shadow"
          >
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <span className="text-3xl">{integration.logo}</span>
                <div>
                  <h3 className="font-semibold text-foreground">{integration.name}</h3>
                  {integration.connected ? (
                    <span className="inline-flex items-center gap-1.5 text-xs text-success">
                      <span className="w-1.5 h-1.5 rounded-full bg-success" />
                      Connected
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                      <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground" />
                      Not connected
                    </span>
                  )}
                </div>
              </div>
            </div>

            <p className="text-sm text-muted-foreground mb-4">{integration.description}</p>

            {integration.connected && integration.details && (
              <div className="bg-secondary/50 rounded-xl p-3 mb-4 text-sm">
                <p className="text-foreground font-medium">{integration.details.portal}</p>
                <p className="text-muted-foreground">{integration.details.email}</p>
                <div className="flex items-center gap-2 mt-2">
                  {integration.details.permissions?.map((perm) => (
                    <span key={perm} className="inline-flex items-center gap-1 text-xs text-success">
                      <Check className="h-3 w-3" />
                      {perm}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {integration.connected ? (
              <div className="flex items-center gap-2">
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="flex-1"
                  onClick={() => handleDisconnect(integration.id)}
                >
                  Disconnect
                </Button>
                <Button 
                  variant="ghost" 
                  size="sm"
                  onClick={() => handleTestConnection(integration.id)}
                >
                  <RefreshCw className="h-4 w-4 mr-1" />
                  Test
                </Button>
              </div>
            ) : (
              <Button 
                size="sm" 
                className="w-full"
                onClick={() => handleConnect(integration.id)}
              >
                Connect
              </Button>
            )}

            {integration.lastSync && (
              <p className="text-xs text-muted-foreground mt-3 text-center">
                Last synced {integration.lastSync}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default IntegrationsPage;
