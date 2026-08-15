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
  /** Lost reasons shown in the extension's Lost picker (plus a UI-only "Other"). */
  lost_reasons?: string[];
  /**
   * Confirmed override for the deal property that stores the portal's
   * closed-lost reason. Leave unset/null to let sync auto-detect it from the
   * live deal schema on every call.
   */
  lost_reason_deal_property?: string | null;
  /**
   * This account's own hs_lead_status option value that means "Lost" /
   * "On hold" - chosen by the admin from their EXISTING options (see
   * backend/app/services/hubspot/call_outcome.py module docstring for why
   * Vocify never creates new options itself). null/unset means not
   * configured: the extension doesn't show that button until it is.
   */
  lost_lead_status_value?: string | null;
  on_hold_lead_status_value?: string | null;
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

  async getPreview(
    memoId: string,
    dealId?: string,
    opts?: { createNewDeal?: boolean; contactId?: string }
  ) {
    const params = new URLSearchParams();
    if (dealId) params.set("deal_id", dealId);
    if (opts?.createNewDeal) params.set("create_new_deal", "true");
    if (opts?.contactId) params.set("contact_id", opts.contactId);
    const qs = params.toString();
    const endpoint = `/memos/${memoId}/preview${qs ? `?${qs}` : ""}`;
    return api.get(endpoint);
  },

  /** Get preview with optional edited extraction (user edits before confirming) */
  async getPreviewWithExtraction(
    memoId: string,
    dealId?: string,
    extraction?: object,
    opts?: { createNewDeal?: boolean; contactId?: string }
  ) {
    return api.post(`/memos/${memoId}/preview`, {
      deal_id: dealId || undefined,
      create_new_deal: opts?.createNewDeal || false,
      contact_id: opts?.contactId || undefined,
      extraction: extraction || undefined,
    });
  },

  async approveSync(
    memoId: string,
    dealId?: string,
    isNewDeal: boolean = false,
    extraction?: any,
    opts?: { contactId?: string; companyId?: string; skipDeal?: boolean }
  ) {
    return api.post(`/memos/${memoId}/approve`, {
      deal_id: dealId,
      is_new_deal: isNewDeal,
      extraction: extraction,
      contact_id: opts?.contactId,
      company_id: opts?.companyId,
      skip_deal: opts?.skipDeal || false,
    });
  },
};

