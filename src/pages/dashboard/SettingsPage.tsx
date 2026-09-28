import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, Unplug } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { integrationKeys } from "@/features/integrations/api";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi, crmKeys, SESSION_QUERY_STALE_MS } from "@/lib/api/crm";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { IconAction } from "@/components/ui/icon-action";
import { VocifyLoader } from "@/components/ui/vocify-loader";
import { HubSpotConfiguration } from "@/components/dashboard/hubspot/HubSpotConfiguration";
import { HubSpotConnection } from "@/components/dashboard/hubspot/HubSpotConnection";
import { SalesforceConfiguration } from "@/components/dashboard/salesforce/SalesforceConfiguration";
import { SalesforceConnection } from "@/components/dashboard/salesforce/SalesforceConnection";
import { PipedriveConfiguration } from "@/components/dashboard/pipedrive/PipedriveConfiguration";
import { PipedriveConnection } from "@/components/dashboard/pipedrive/PipedriveConnection";

type LiveCrmId = "hubspot" | "salesforce" | "pipedrive";

const CRM_LABEL: Record<LiveCrmId, string> = {
  hubspot: "HubSpot",
  salesforce: "Salesforce",
  pipedrive: "Pipedrive",
};

const LIVE: { id: LiveCrmId; name: string; description: string; logo: string }[] = [
  {
    id: "hubspot",
    name: "HubSpot",
    description: "Deals, contacts, and call activities",
    logo: "https://cdn.worldvectorlogo.com/logos/hubspot.svg",
  },
  {
    id: "salesforce",
    name: "Salesforce",
    description: "Opportunities and contacts",
    logo: "https://cdn.worldvectorlogo.com/logos/salesforce-2.svg",
  },
  {
    id: "pipedrive",
    name: "Pipedrive",
    description: "Deals, people, and organizations",
    logo: "https://cdn.worldvectorlogo.com/logos/pipedrive.svg",
  },
];

function oauthErrorMessage(params: URLSearchParams): string | null {
  const hubspot = params.get("hubspot");
  const salesforce = params.get("salesforce");
  const pipedrive = params.get("pipedrive");
  const error = params.get("error");
  if (!(hubspot === "error" || salesforce === "error" || pipedrive === "error" || error)) return null;

  const errDesc = params.get("error_description");
  const decoded = errDesc ? decodeURIComponent(errDesc.replace(/\+/g, " ")) : "";
  const sfErrors: Record<string, string> = {
    missing_params: "Salesforce did not return authorization. Try again.",
    invalid_state: "Session expired. Please try connecting again.",
    token_exchange_failed:
      "Could not complete Salesforce login. Check that the Callback URL matches SALESFORCE_REDIRECT_URI.",
    no_token: "Salesforce did not return tokens. Enable API and refresh_token scopes.",
    validation_failed: "Salesforce login worked but API access failed.",
    save_failed: "Could not save the connection.",
    invalid_scope: "Salesforce rejected the requested scopes.",
    OAUTH_EC_APP_NOT_FOUND: "Salesforce does not recognize this OAuth app.",
  };

  const pdErrors: Record<string, string> = {
    missing_params: "Pipedrive did not return authorization. Try again.",
    invalid_state: "Session expired. Please try connecting again.",
    token_exchange_failed:
      "Could not complete Pipedrive login. Check that the Callback URL matches PIPEDRIVE_REDIRECT_URI.",
    no_token: "Pipedrive did not return tokens. Confirm the Marketplace app scopes.",
    validation_failed: "Pipedrive login worked but API access failed.",
    save_failed: "Could not save the connection.",
    user_denied: "Pipedrive authorization was cancelled.",
  };

  if (error === "invalid_state") return sfErrors.invalid_state;
  if (pipedrive === "error") {
    if (error && pdErrors[error]) return pdErrors[error];
    if (decoded) return `Pipedrive: ${decoded}`;
    if (error && error !== "error") return `Failed to connect Pipedrive (${error}).`;
    return "Failed to connect Pipedrive.";
  }
  if (salesforce === "error") {
    if (error && sfErrors[error]) return sfErrors[error];
    if (decoded.toLowerCase().includes("not installed")) {
      return "This Salesforce app is not installed in the org you signed into.";
    }
    if (decoded) return `Salesforce: ${decoded}`;
    if (error && error !== "error") return `Failed to connect Salesforce (${error}).`;
    return "Failed to connect Salesforce.";
  }
  return "Failed to connect HubSpot.";
}

const SettingsPage = () => {
  const { user } = useAuth();
  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [connectId, setConnectId] = useState<LiveCrmId | null>(null);
  const [disconnectId, setDisconnectId] = useState<LiveCrmId | null>(null);

  const { data: connections = [], isLoading: connectionsLoading } = useQuery({
    queryKey: crmKeys.connections(),
    queryFn: async () => {
      const { connections: rows } = await crmApi.listConnections();
      return (rows || []).filter((c) => c.status === "connected");
    },
    staleTime: SESSION_QUERY_STALE_MS,
  });

  const { data: prefs } = useQuery({
    queryKey: crmKeys.preferences(),
    queryFn: () => crmApi.getCrmPreferences(),
    staleTime: SESSION_QUERY_STALE_MS,
  });

  const primaryConnectionId = prefs?.primary_crm_connection_id ?? null;
  const hubspot = connections.find((c) => c.provider === "hubspot");
  const salesforce = connections.find((c) => c.provider === "salesforce");
  const pipedrive = connections.find((c) => c.provider === "pipedrive");
  const byProvider = { hubspot, salesforce, pipedrive };

  const refreshCrm = () => {
    queryClient.invalidateQueries({ queryKey: crmKeys.all });
    queryClient.invalidateQueries({ queryKey: integrationKeys.all });
  };

  useEffect(() => {
    const hubspotStatus = searchParams.get("hubspot");
    const salesforceStatus = searchParams.get("salesforce");
    const pipedriveStatus = searchParams.get("pipedrive");
    if (hubspotStatus === "connected") {
      toast.success("HubSpot connected");
      setSearchParams({}, { replace: true });
      refreshCrm();
      return;
    }
    if (salesforceStatus === "connected") {
      toast.success("Salesforce connected");
      setSearchParams({}, { replace: true });
      refreshCrm();
      return;
    }
    if (pipedriveStatus === "connected") {
      toast.success("Pipedrive connected");
      setSearchParams({}, { replace: true });
      refreshCrm();
      return;
    }
    const err = oauthErrorMessage(searchParams);
    if (err) {
      toast.error(err, { duration: 12_000 });
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to the OAuth return query
  }, [searchParams]);

  const primaryMutation = useMutation({
    mutationFn: (id: string) => crmApi.setPrimaryCrmConnection(id),
    onSuccess: (_, id) => {
      queryClient.setQueryData(crmKeys.preferences(), { primary_crm_connection_id: id });
      toast.success("Primary CRM updated");
    },
    onError: () => toast.error("Could not update primary CRM"),
  });

  const disconnectMutation = useMutation({
    mutationFn: async (id: LiveCrmId) => {
      if (id === "hubspot") await crmApi.disconnectHubSpot();
      else if (id === "salesforce") await crmApi.disconnectSalesforce();
      else await crmApi.disconnectPipedrive();
    },
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: crmKeys.connections() });
      const previous = queryClient.getQueryData(crmKeys.connections());
      queryClient.setQueryData(
        crmKeys.connections(),
        (rows: { provider: string }[] | undefined) => (rows || []).filter((row) => row.provider !== id),
      );
      const setupKey =
        id === "hubspot"
          ? crmKeys.hubspotSetup()
          : id === "salesforce"
            ? crmKeys.salesforceSetup()
            : crmKeys.pipedriveSetup();
      await queryClient.cancelQueries({ queryKey: setupKey });
      queryClient.removeQueries({ queryKey: setupKey });
      setDisconnectId(null);
      return { previous };
    },
    onSuccess: () => {
      toast.success("Disconnected");
      queryClient.invalidateQueries({ queryKey: crmKeys.connections() });
      queryClient.invalidateQueries({ queryKey: crmKeys.preferences() });
    },
    onError: (_error, _id, context) => {
      if (context?.previous) queryClient.setQueryData(crmKeys.connections(), context.previous);
      toast.error("Failed to disconnect");
    },
  });

  const refreshPermissions = useMutation({
    mutationFn: async () => {
      const { redirect_url } = await crmApi.getHubSpotAuthorizeUrl();
      window.location.href = redirect_url;
    },
    onError: (error: unknown) => {
      const msg =
        error && typeof error === "object" && "data" in error
          ? String((error as { data?: { detail?: string } }).data?.detail ?? "Failed to refresh HubSpot permissions")
          : "Failed to refresh HubSpot permissions";
      toast.error(msg);
    },
  });

  if (connectionsLoading) {
    return (
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" label="Loading CRM..." />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`}>
        <div className="mb-6">
          <h2 className={THEME_TOKENS.typography.sectionTitle}>CRM</h2>
          <p className="text-sm text-muted-foreground mt-1">
            {canManage
              ? "Connect a CRM, then choose the pipeline and fields AI may fill."
              : "Workspace CRM. Ask an admin to connect or change it."}
          </p>
        </div>

        {canManage && connections.length > 1 && (
          <div className="mb-6">
            <p className={`${THEME_TOKENS.typography.capsLabel} mb-2`}>Primary for memo sync</p>
            <div className="inline-flex rounded-full border border-border/40 bg-secondary/5 p-1">
              {connections.map((c) => {
                const selected = primaryConnectionId === c.id;
                const label = CRM_LABEL[c.provider as LiveCrmId] ?? c.provider;
                return (
                  <button
                    key={c.id}
                    type="button"
                    aria-pressed={selected}
                    disabled={primaryMutation.isPending}
                    onClick={() => primaryMutation.mutate(c.id)}
                    className={`rounded-full px-4 h-8 text-xs transition-colors ${
                      selected ? "bg-beige text-cream" : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="divide-y divide-border/40">
          {LIVE.map((item) => {
            const connection = byProvider[item.id];
            const connected = Boolean(connection);
            const isPrimary =
              Boolean(connection) &&
              connections.length > 1 &&
              primaryConnectionId === connection?.id;

            return (
              <div key={item.id} className="flex items-center gap-4 py-4 first:pt-0 last:pb-0">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-secondary/5 p-2">
                  <img src={item.logo} alt="" className="h-full w-full object-contain" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-foreground">{item.name}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {connected ? (
                      <span className="text-success">
                        Connected{isPrimary ? " · primary" : ""}
                      </span>
                    ) : (
                      item.description
                    )}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {connected ? (
                    <>
                      {canManage && item.id === "hubspot" && (
                        <IconAction
                          label="Refresh HubSpot permissions"
                          pendingLabel="Redirecting…"
                          pending={refreshPermissions.isPending}
                          onClick={() => refreshPermissions.mutate()}
                        >
                          <ShieldCheck className="h-4 w-4" />
                        </IconAction>
                      )}
                      {canManage && (
                        <IconAction
                          label={`Disconnect ${item.name}`}
                          tone="danger"
                          onClick={() => setDisconnectId(item.id)}
                        >
                          <Unplug className="h-4 w-4" />
                        </IconAction>
                      )}
                    </>
                  ) : canManage ? (
                    <Button
                      size="sm"
                      className="rounded-full bg-beige text-cream h-9 px-4"
                      onClick={() => setConnectId(item.id)}
                    >
                      Connect
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">Not connected</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {hubspot && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`}>
          <div className="mb-6">
            <h2 className={THEME_TOKENS.typography.sectionTitle}>HubSpot fields</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {canManage
                ? "Pipeline, who gets credit, and whether Vocify writes after processing — HubSpot recordings, the Vocify dialer, and memos locked to a contact. Or wait for Approve."
                : "Workspace field mapping. Ask an admin to change it."}
            </p>
          </div>
          <HubSpotConfiguration readOnly={!canManage} />
        </div>
      )}

      {salesforce && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`}>
          <div className="mb-6">
            <h2 className={THEME_TOKENS.typography.sectionTitle}>Salesforce fields</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {canManage
                ? "Default stage, fields AI may fill, and whether Vocify writes after processing — or waits for Approve."
                : "Workspace field mapping. Ask an admin to change it."}
            </p>
          </div>
          <SalesforceConfiguration readOnly={!canManage} />
        </div>
      )}

      {pipedrive && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`}>
          <div className="mb-6">
            <h2 className={THEME_TOKENS.typography.sectionTitle}>Pipedrive fields</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {canManage
                ? "Default pipeline and stage, fields AI may fill, and whether Vocify writes after processing — or waits for Approve."
                : "Workspace field mapping. Ask an admin to change it."}
            </p>
          </div>
          <PipedriveConfiguration readOnly={!canManage} />
        </div>
      )}

      <Dialog open={connectId !== null} onOpenChange={(open) => !open && setConnectId(null)}>
        <DialogContent className={`${THEME_TOKENS.radius.container} max-w-lg border-border/70 bg-card p-6 md:p-8`}>
          <DialogHeader>
            <DialogTitle className={THEME_TOKENS.typography.sectionTitle}>
              Connect {connectId ? CRM_LABEL[connectId] : ""}
            </DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground">
              You will be redirected to {connectId ? CRM_LABEL[connectId] : "the CRM"} to authorize API access.
            </DialogDescription>
          </DialogHeader>
          {connectId === "salesforce" ? (
            <SalesforceConnection
              onConnected={() => {
                setConnectId(null);
                refreshCrm();
              }}
            />
          ) : connectId === "pipedrive" ? (
            <PipedriveConnection
              onConnected={() => {
                setConnectId(null);
                refreshCrm();
              }}
            />
          ) : (
            <HubSpotConnection
              onConnected={() => {
                setConnectId(null);
                refreshCrm();
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      <ConfirmAction
        open={disconnectId !== null}
        onOpenChange={(open) => !open && setDisconnectId(null)}
        title={`Disconnect ${disconnectId ? CRM_LABEL[disconnectId] : "CRM"}?`}
        description="Saved field mapping and sync history for this CRM will be removed."
        confirmLabel="Disconnect"
        pending={disconnectMutation.isPending}
        onConfirm={() => {
          if (disconnectId) disconnectMutation.mutate(disconnectId);
        }}
      />
    </div>
  );
};

export default SettingsPage;
