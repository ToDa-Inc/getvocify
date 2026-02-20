import { api } from "@/shared/lib/api-client";

export interface Pipeline {
  id: string;
  label: string;
  stages: { id: string; label: string }[];
}

export interface CRMSchema {
  object_type: string;
  properties: { name: string; label: string; type: string; options?: { label: string; value: string }[] }[];
}

export interface CRMConfiguration {
  default_pipeline_id: string;
  default_pipeline_name: string;
  default_stage_id: string;
  default_stage_name: string;
  allowed_deal_fields: string[];
  allowed_contact_fields: string[];
  allowed_company_fields: string[];
  auto_create_contacts: boolean;
  auto_create_companies: boolean;
}

export const crmApi = {
  /** OAuth: Get HubSpot authorize URL, then redirect user there */
  async getHubSpotAuthorizeUrl(): Promise<{ redirect_url: string }> {
    return api.get<{ redirect_url: string }>("/crm/hubspot/authorize");
  },

  async connectHubSpot(accessToken: string) {
    return api.post("/crm/hubspot/connect", { access_token: accessToken });
  },

  async disconnectHubSpot() {
    return api.delete("/crm/hubspot/disconnect");
  },

  async getPipelines() {
    return api.get<Pipeline[]>("/crm/hubspot/pipelines");
  },

  async getConfiguration() {
    try {
      return await api.get<CRMConfiguration>("/crm/hubspot/configuration");
    } catch (error: any) {
      if (error.status === 404) return null;
      throw error;
    }
  },

  async saveConfiguration(config: CRMConfiguration) {
    return api.post("/crm/hubspot/configure", config);
  },

  async getSchema(objectType: "deals" | "contacts" | "companies") {
    return api.get<CRMSchema>(`/crm/hubspot/schema?object_type=${objectType}`);
  },

  async searchDeals(query: string) {
    return api.get<any[]>(`/crm/hubspot/search/deals?q=${encodeURIComponent(query)}`);
  },

  async findMatches(memoId: string) {
    return api.post(`/memos/${memoId}/match`);
  },

  async getPreview(memoId: string, dealId?: string) {
    const endpoint = `/memos/${memoId}/preview${dealId ? `?deal_id=${dealId}` : ""}`;
    return api.get(endpoint);
  },

  async approveSync(memoId: string, dealId?: string, isNewDeal: boolean = false, extraction?: any) {
    return api.post(`/memos/${memoId}/approve`, {
      deal_id: dealId,
      is_new_deal: isNewDeal,
      extraction: extraction,
    });
  },
};

