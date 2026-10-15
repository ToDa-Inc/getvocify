import { useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ShieldCheck, Unplug } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi, crmKeys, SESSION_QUERY_STALE_MS } from "@/lib/api/crm";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { SettingsRow, SettingsSection } from "@/components/ui/settings-card";
import { VocifyLoader } from "@/components/ui/vocify-loader";
import { HubSpotConfiguration } from "@/components/dashboard/hubspot/HubSpotConfiguration";
import { HubSpotFieldPermissions } from "@/components/dashboard/hubspot/HubSpotFieldPermissions";
import { SalesforceConfiguration } from "@/components/dashboard/salesforce/SalesforceConfiguration";
import { PipedriveConfiguration } from "@/components/dashboard/pipedrive/PipedriveConfiguration";
import { CRM_LABEL, CRM_PROVIDERS, isLiveCrmId } from "./crmProviders";

/** What each CRM's settings do, in the words this page has always used for it. */
const HOW_IT_WORKS: Record<string, { manage: string; read: string }> = {
  hubspot: {
    manage:
      "Pipeline, who gets credit, and whether Vocify writes after processing — HubSpot recordings, the Vocify dialer, and memos locked to a contact. Or wait for Approve.",
    read: "Workspace field mapping. Ask an admin to change it.",
  },
  salesforce: {
    manage: "Default stage, fields AI may fill, and whether Vocify writes after processing — or waits for Approve.",
    read: "Workspace field mapping. Ask an admin to change it.",
  },
  pipedrive: {
    manage:
      "Default pipeline and stage, fields AI may fill, and whether Vocify writes after processing — or waits for Approve.",
    read: "Workspace field mapping. Ask an admin to change it.",
  },
};

/** One connected CRM: what it is, how it works, its settings, and the connection itself (refresh, disconnect). */
const CrmProviderPage = () => {
  const { provider } = useParams();
  const id = isLiveCrmId(provider) ? provider : null;
  const { user } = useAuth();
  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [disconnectOpen, setDisconnectOpen] = useState(false);

  const { data: connections, isLoading } = useQuery({
    queryKey: crmKeys.connections(),
    queryFn: async () => {
      const { connections: rows } = await crmApi.listConnections();
      return (rows || []).filter((c) => c.status === "connected");
    },
    staleTime: SESSION_QUERY_STALE_MS,
  });

  const disconnectMutation = useMutation({
    mutationFn: async () => {
      if (!id) return;
      if (id === "hubspot") await crmApi.disconnectHubSpot();
      else if (id === "salesforce") await crmApi.disconnectSalesforce();
      else await crmApi.disconnectPipedrive();
    },
    onMutate: async () => {
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
      setDisconnectOpen(false);
      return { previous };
    },
    onSuccess: () => {
      toast.success("Disconnected");
      queryClient.invalidateQueries({ queryKey: crmKeys.connections() });
      queryClient.invalidateQueries({ queryKey: crmKeys.preferences() });
      navigate("/dashboard/settings/crm", { replace: true });
    },
    onError: (_error, _vars, context) => {
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


  if (!id) return <Navigate to="/dashboard/settings/crm" replace />;
  if (isLoading) {
    return (
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" label="Loading CRM..." />
      </div>
    );
  }
  if (!connections?.some((c) => c.provider === id)) return <Navigate to="/dashboard/settings/crm" replace />;

  const item = CRM_PROVIDERS.find((p) => p.id === id)!;
  const how = canManage ? HOW_IT_WORKS[id].manage : HOW_IT_WORKS[id].read;

  return (
    <div className="mx-auto max-w-[680px] space-y-8">
      <div className="space-y-4">
        <Link
          to="/dashboard/settings/crm"
          className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
          CRM
        </Link>
        <div className="flex items-center gap-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-secondary/10 p-2">
            <img src={item.logo} alt="" className="h-full w-full object-contain" />
          </span>
          <div className="min-w-0">
            <h2 className={THEME_TOKENS.typography.sectionTitle}>{item.name}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">{item.description}</p>
          </div>
        </div>
        <p className="text-sm text-muted-foreground">{how}</p>
      </div>

      <SettingsSection>
        <div className="py-5">
          {id === "hubspot" && <HubSpotConfiguration readOnly={!canManage} />}
          {id === "salesforce" && <SalesforceConfiguration readOnly={!canManage} />}
          {id === "pipedrive" && <PipedriveConfiguration readOnly={!canManage} />}
        </div>
      </SettingsSection>

      {id === "hubspot" && canManage && (
        <SettingsSection>
          <div className="py-5">
            <HubSpotFieldPermissions />
          </div>
        </SettingsSection>
      )}

      {canManage && (
        <SettingsSection>
          {id === "hubspot" && (
            <SettingsRow icon={ShieldCheck} title="Refresh HubSpot permissions">
              <Button
                size="sm"
                variant="outline"
                className="rounded-full"
                disabled={refreshPermissions.isPending}
                onClick={() => refreshPermissions.mutate()}
              >
                {refreshPermissions.isPending ? "Redirecting…" : "Refresh"}
              </Button>
            </SettingsRow>
          )}
          <SettingsRow
            icon={Unplug}
            title={`Disconnect ${CRM_LABEL[id]}`}
            description="Saved field mapping and sync history for this CRM will be removed."
          >
            <Button size="sm" variant="dangerGhost" className="rounded-full" onClick={() => setDisconnectOpen(true)}>
              Disconnect
            </Button>
          </SettingsRow>
        </SettingsSection>
      )}

      <ConfirmAction
        open={disconnectOpen}
        onOpenChange={setDisconnectOpen}
        title={`Disconnect ${CRM_LABEL[id]}?`}
        description="Saved field mapping and sync history for this CRM will be removed."
        confirmLabel="Disconnect"
        pending={disconnectMutation.isPending}
        onConfirm={() => disconnectMutation.mutate()}
      />
    </div>
  );
};

export default CrmProviderPage;
