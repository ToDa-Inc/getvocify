import { useIntegrations } from "@/features/integrations/hooks/useIntegrations";
import { contactRecordUrl } from "@/lib/today";

/** Where a memo's linked contact lives in the company's CRM: null when it is not HubSpot or has no portal. */
export function useCrmContactLink(contactId: string | null | undefined): { url: string | null; name: string } {
  const { data } = useIntegrations();
  const hubspot = data?.find((connection) => connection.provider === "hubspot" && connection.status === "connected");
  return {
    url: contactRecordUrl(hubspot ? "hubspot" : null, hubspot?.metadata?.portalId ?? null, contactId ?? null),
    name: "HubSpot",
  };
}
