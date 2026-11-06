import { useIntegrations } from "@/features/integrations/hooks/useIntegrations";
import { CRM_PROVIDER_CONFIGS, type CRMProvider } from "@/features/integrations/types";
import { contactRecordUrl } from "@/lib/today";

/** Where a memo's linked contact lives in the company's CRM (HubSpot or Pipedrive): null url when it is neither or has no link. */
export function useCrmContactLink(contactId: string | null | undefined): { url: string | null; name: string } {
  const { data } = useIntegrations();
  const crm = data?.find((connection) => (connection.provider === "hubspot" || connection.provider === "pipedrive") && connection.status === "connected");
  return {
    url: contactRecordUrl(crm?.provider ?? null, crm?.metadata?.portalId ?? null, contactId ?? null, crm?.metadata),
    name: crm ? CRM_PROVIDER_CONFIGS[crm.provider as CRMProvider].name : "the CRM",
  };
}
