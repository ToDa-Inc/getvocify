import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { integrationKeys } from "@/features/integrations/api";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { SettingsRow, SettingsSection } from "@/components/ui/settings-card";
import { crmApi, crmKeys, SESSION_QUERY_STALE_MS } from "@/lib/api/crm";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { VocifyLoader } from "@/components/ui/vocify-loader";
import { HubSpotConnection } from "@/components/dashboard/hubspot/HubSpotConnection";
import { SalesforceConnection } from "@/components/dashboard/salesforce/SalesforceConnection";
import { PipedriveConnection } from "@/components/dashboard/pipedrive/PipedriveConnection";

import { CRM_LABEL, CRM_PROVIDERS, type LiveCrmId } from "./settings/crmProviders";

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
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [connectId, setConnectId] = useState<LiveCrmId | null>(null);

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
  const byProvider = {
    hubspot: connections.find((c) => c.provider === "hubspot"),
    salesforce: connections.find((c) => c.provider === "salesforce"),
    pipedrive: connections.find((c) => c.provider === "pipedrive"),
  };

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

  if (connectionsLoading) {
    return (
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" label="Loading CRM..." />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[680px] space-y-8">
      {canManage && connections.length > 1 && (
        <SettingsSection>
          <SettingsRow title="Primary for memo sync">
            <Segmented<string>
              value={primaryConnectionId ?? ""}
              onValueChange={(id) => primaryMutation.mutate(id)}
              options={connections.map((c) => ({
                value: c.id,
                label: CRM_LABEL[c.provider as LiveCrmId] ?? c.provider,
              }))}
              aria-label="Primary CRM"
              className={primaryMutation.isPending ? "opacity-50" : ""}
            />
          </SettingsRow>
        </SettingsSection>
      )}

      <SettingsSection label="CRM">
        {CRM_PROVIDERS.map((item) => {
          const connection = byProvider[item.id];
          if (connection) {
            const isPrimary = connections.length > 1 && primaryConnectionId === connection.id;
            return (
              <SettingsRow
                key={item.id}
                logo={item.logo}
                title={item.name}
                description={item.description}
                value={<span className="text-success">Connected{isPrimary ? " · primary" : ""}</span>}
                onClick={() => navigate(`/dashboard/settings/crm/${item.id}`)}
              />
            );
          }
          return (
            <SettingsRow key={item.id} logo={item.logo} title={item.name} description={item.description}>
              {canManage ? (
                <Button size="sm" className="rounded-full bg-beige text-cream h-9 px-4" onClick={() => setConnectId(item.id)}>
                  Connect
                </Button>
              ) : (
                <span className="text-xs text-muted-foreground">Not connected</span>
              )}
            </SettingsRow>
          );
        })}
      </SettingsSection>
      {!canManage && <p className="px-1 text-xs text-muted-foreground">Workspace CRM. Ask an admin to connect or change it.</p>}

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

    </div>
  );
};

export default SettingsPage;
