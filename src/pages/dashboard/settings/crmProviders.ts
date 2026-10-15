export type LiveCrmId = "hubspot" | "salesforce" | "pipedrive";

export const CRM_LABEL: Record<LiveCrmId, string> = {
  hubspot: "HubSpot",
  salesforce: "Salesforce",
  pipedrive: "Pipedrive",
};

export const CRM_PROVIDERS: { id: LiveCrmId; name: string; description: string; logo: string }[] = [
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

export function isLiveCrmId(value: string | undefined): value is LiveCrmId {
  return value === "hubspot" || value === "salesforce" || value === "pipedrive";
}
