import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { QueueStatesPicker } from "@/components/dashboard/crm/QueueStatesPicker";
import { crmApi, crmKeys, SESSION_QUERY_STALE_MS, type CRMConfiguration } from "@/lib/api/crm";
import { loadHubSpotSetup } from "@/lib/api/hubspot-setup";
import { loadPipedriveSetup } from "@/lib/api/pipedrive-setup";
import { prepareQueueStatesForSave, type CrmProvider } from "@/lib/queue-states";
import { useLanguage } from "@/lib/i18n";

type ConnectedProvider = "hubspot" | "pipedrive";

export function SdrExitSettings() {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<CRMConfiguration | null>(null);
  const [saving, setSaving] = useState(false);

  const connections = useQuery({
    queryKey: crmKeys.connections(),
    queryFn: async () => {
      const { connections } = await crmApi.listConnections();
      return (connections || []).filter((item) => item.status === "connected");
    },
    staleTime: SESSION_QUERY_STALE_MS,
  });

  const provider: ConnectedProvider | null = connections.data?.some((item) => item.provider === "hubspot")
    ? "hubspot"
    : connections.data?.some((item) => item.provider === "pipedrive")
      ? "pipedrive"
      : null;

  const hubspot = useQuery({
    queryKey: crmKeys.hubspotSetup(),
    queryFn: () => loadHubSpotSetup(false),
    enabled: provider === "hubspot",
    staleTime: SESSION_QUERY_STALE_MS,
  });
  const pipedrive = useQuery({
    queryKey: crmKeys.pipedriveSetup(),
    queryFn: () => loadPipedriveSetup(false),
    enabled: provider === "pipedrive",
    staleTime: SESSION_QUERY_STALE_MS,
  });

  const setup = provider === "hubspot" ? hubspot.data : provider === "pipedrive" ? pipedrive.data : undefined;
  if (!provider || !setup?.config.queue_states_enabled) return null;

  const config = draft ?? setup.config;
  const crmProvider: CrmProvider = provider;

  const save = async () => {
    setSaving(true);
    try {
      const queueStates = prepareQueueStatesForSave({
        provider: crmProvider,
        source: config.queue_state_source,
        booked: config.queue_booked_states ?? [],
        ended: config.queue_ended_states ?? [],
        pipelines: setup.pipelines,
        contactSchema: provider === "hubspot" ? setup.schemas.contacts : undefined,
        pipedriveStatusLabels: {
          won: t.product.queueStateWon,
          lost: t.product.queueStateLost,
        },
      });
      const payload = { ...setup.config, ...queueStates };
      if (provider === "hubspot") {
        await crmApi.saveConfiguration(payload);
        queryClient.setQueryData(crmKeys.hubspotSetup(), (prev) =>
          prev ? { ...prev, config: payload } : prev,
        );
      } else {
        await crmApi.savePipedriveConfiguration(payload);
        queryClient.setQueryData(crmKeys.pipedriveSetup(), (prev) =>
          prev ? { ...prev, config: payload } : prev,
        );
      }
      setDraft(null);
      toast.success(t.product.queueExitSaved);
    } catch {
      toast.error(t.product.queueExitSaveFailed);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3 border-b border-border/15 pb-5">
      <QueueStatesPicker
        provider={crmProvider}
        config={config}
        pipelines={setup.pipelines}
        contactSchema={provider === "hubspot" ? setup.schemas.contacts : undefined}
        onChange={(patch) => setDraft((prev) => ({ ...(prev ?? setup.config), ...patch }))}
      />
      <Button type="button" variant="outline" size="sm" disabled={saving} onClick={() => void save()}>
        {t.product.saveButton}
      </Button>
    </div>
  );
}
