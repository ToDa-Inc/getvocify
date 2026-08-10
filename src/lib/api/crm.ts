import { api, ApiError } from "@/shared/lib/api-client";

export interface Pipeline {
  id: string;
  label: string;
  stages: { id: string; label: string }[];
}

export interface CRMSchema {
  object_type: string;
  properties: { name: string; label: string; type: string; options?: { label: string; value: string }[] }[];
  pipelines?: Pipeline[];
}

export interface CRMConfiguration {
  default_pipeline_id: string;
  default_pipeline_name: string;
  default_stage_id: string;
  default_stage_name: string;
  allowed_deal_fields: string[];
  allowed_contact_fields: string[];
  allowed_company_fields: string[];
  allowed_line_item_fields?: string[];
  auto_create_contacts: boolean;
  auto_create_companies: boolean;
}

export const crmApi = {
  async listConnections(): Promise<{
    connections: { id: string; provider: string; status: string; created_at?: string }[];
  }> {
    return api.get("/crm/connections");
  },

  async getCrmPreferences(): Promise<{ primary_crm_connection_id: string | null }> {
    return api.get("/crm/preferences");
  },

  async setPrimaryCrmConnection(connectionId: string) {
    return api.put(`/crm/primary?connection_id=${encodeURIComponent(connectionId)}`, {});
  },

  /**
   * Deal/opportunity search for manual picker: uses primary CRM (or sole connection).
   */
  async searchCrmDeals(query: string) {
    const prefs = await this.getCrmPreferences();
    const { connections } = await this.listConnections();
    const ok = (connections || []).filter((c) => c.status === "connected");
    if (ok.length === 0) return [];
    let target = ok.find((c) => c.id === prefs.primary_crm_connection_id);
    if (!target && ok.length === 1) target = ok[0];
    if (!target) {
      throw new ApiError(
        400,
        { detail: "Multiple CRMs connected. Choose a primary CRM in Integrations." },
        "Multiple CRMs connected. Choose a primary CRM in Integrations.",
      );
    }
    if (target.provider === "salesforce") {
      return api.get<any[]>(`/crm/salesforce/search/opportunities?q=${encodeURIComponent(query)}`);
    }
    return api.get<any[]>(`/crm/hubspot/search/deals?q=${encodeURIComponent(query)}`);
  },

  /** OAuth: Get HubSpot authorize URL, then redirect user there */
  async getHubSpotAuthorizeUrl(): Promise<{ redirect_url: string }> {
    return api.get<{ redirect_url: string }>("/crm/hubspot/authorize");
  },

  async getSalesforceAuthorizeUrl(): Promise<{ redirect_url: string }> {
    return api.get<{ redirect_url: string }>("/crm/salesforce/authorize");
  },

  async disconnectSalesforce() {
    return api.delete("/crm/salesforce/disconnect");
  },

  async getSalesforceConfiguration() {
    try {
      return await api.get<CRMConfiguration>("/crm/salesforce/configuration");
    } catch (error: any) {
      if (error.status === 404) return null;
      throw error;
    }
  },

  async saveSalesforceConfiguration(config: CRMConfiguration) {
    return api.post("/crm/salesforce/configure", config);
  },

  async getSalesforceSchema() {
    return api.get<CRMSchema>("/crm/salesforce/schema");
  },

  async getSalesforceStages(): Promise<{ id: string; label: string; display_order?: number }[]> {
    return api.get("/crm/salesforce/stages");
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

  async getSchema(objectType: "deals" | "contacts" | "companies" | "line_items") {
    return api.get<CRMSchema>(`/crm/hubspot/schema?object_type=${objectType}`);
  },

  async searchDeals(query: string) {
    return api.get<any[]>(`/crm/hubspot/search/deals?q=${encodeURIComponent(query)}`);
  },

  /** Get deal context for pre-filling extraction when user is on a deal page */
  async getDealContext(dealId: string) {
    return api.get<{
      companyName?: string | null;
      contactName?: string | null;
      contactEmail?: string | null;
      raw_extraction?: Record<string, unknown>;
    }>(`/crm/hubspot/deals/${dealId}/context`);
  },

  async findMatches(memoId: string): Promise<{ deal_id: string; deal_name: string; [key: string]: unknown }[]> {
    return api.post(`/memos/${memoId}/match`);
  },

  async getPreview(memoId: string, dealId?: string) {
    const endpoint = `/memos/${memoId}/preview${dealId ? `?deal_id=${dealId}` : ""}`;
    return api.get(endpoint);
  },

  /** Get preview with optional edited extraction (user edits before confirming) */
  async getPreviewWithExtraction(memoId: string, dealId?: string, extraction?: object) {
    return api.post(`/memos/${memoId}/preview`, {
      deal_id: dealId || undefined,
      extraction: extraction || undefined,
    });
  },

  async approveSync(memoId: string, dealId?: string, isNewDeal: boolean = false, extraction?: any) {
    return api.post(`/memos/${memoId}/approve`, {
      deal_id: dealId,
      is_new_deal: isNewDeal,
      extraction: extraction,
    });
  },
};

