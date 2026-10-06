import { ApiError } from "@/shared/lib/api-client";
import {
  crmApi,
  type CRMConfiguration,
  type CRMSchema,
  type Pipeline,
} from "@/lib/api/crm";

export type HubSpotObjectTab = "deals" | "contacts" | "companies" | "line_items";

export type HubSpotSetup = {
  pipelines: Pipeline[];
  schemas: Partial<Record<HubSpotObjectTab, CRMSchema>>;
  config: CRMConfiguration;
  lineItemsScopeMissing: boolean;
  lineItemsSchemaError: boolean;
};

export const DEFAULT_HUBSPOT_CONFIG: CRMConfiguration = {
  default_pipeline_id: "",
  default_pipeline_name: "",
  default_stage_id: "",
  default_stage_name: "",
  allowed_deal_fields: ["dealname", "amount", "description", "closedate"],
  allowed_contact_fields: ["firstname", "lastname", "email", "phone"],
  allowed_company_fields: ["name", "domain"],
  allowed_line_item_fields: ["name", "quantity", "price"],
  auto_create_contacts: true,
  auto_create_companies: true,
  lost_reasons: ["No budget", "No response", "Chose a competitor", "Bad timing", "Not a fit"],
  lost_reason_deal_property: null,
  lost_lead_status_value: null,
  on_hold_lead_status_value: null,
  auto_sync_hubspot_calls: false,
};

function lineItemErrorLooksLikeScope(err: unknown): boolean {
  const detail = String(
    err instanceof ApiError
      ? (typeof err.data === "object" &&
        err.data &&
        "detail" in (err.data as object)
          ? (err.data as { detail?: string }).detail
          : err.message)
      : err instanceof Error
        ? err.message
        : err,
  ).toLowerCase();
  return (
    detail.includes("permission") ||
    detail.includes("scope") ||
    detail.includes("deal-line-item")
  );
}

async function fetchHubSpotSchemas(refresh = false) {
  const opts = refresh ? { refresh: true } : undefined;
  const [dealSchema, contactSchema, companySchema, lineItemResult] = await Promise.all([
    crmApi.getSchema("deals", opts),
    crmApi.getSchema("contacts", opts).catch(() => null),
    crmApi.getSchema("companies", opts).catch(() => null),
    crmApi.getSchema("line_items", opts).then(
      (schema) => ({ ok: true as const, schema }),
      (err: unknown) => ({ ok: false as const, err }),
    ),
  ]);
  return { dealSchema, contactSchema, companySchema, lineItemResult };
}

export async function loadHubSpotSetup(refresh = false): Promise<HubSpotSetup> {
  const [schemaBundle, pipelinesData, currentConfig] = await Promise.all([
    fetchHubSpotSchemas(refresh),
    crmApi.getPipelines(),
    crmApi.getConfiguration(),
  ]);

  const lineItemSchema = schemaBundle.lineItemResult.ok
    ? schemaBundle.lineItemResult.schema
    : null;
  const lineItemsScopeMissing = schemaBundle.lineItemResult.ok
    ? false
    : lineItemErrorLooksLikeScope(schemaBundle.lineItemResult.err);
  const lineItemsSchemaError = schemaBundle.lineItemResult.ok
    ? false
    : !lineItemsScopeMissing;

  const pipelines =
    pipelinesData.length > 0
      ? pipelinesData
      : schemaBundle.dealSchema.pipelines ?? [];

  let config = currentConfig
    ? {
        ...currentConfig,
        allowed_line_item_fields: currentConfig.allowed_line_item_fields?.length
          ? currentConfig.allowed_line_item_fields
          : ["name", "quantity", "price"],
        lost_reasons: currentConfig.lost_reasons?.length
          ? currentConfig.lost_reasons
          : DEFAULT_HUBSPOT_CONFIG.lost_reasons,
        lost_reason_deal_property: currentConfig.lost_reason_deal_property ?? null,
        lost_lead_status_value: currentConfig.lost_lead_status_value ?? null,
        on_hold_lead_status_value: currentConfig.on_hold_lead_status_value ?? null,
        auto_sync_hubspot_calls: currentConfig.auto_sync_hubspot_calls ?? false,
      }
    : { ...DEFAULT_HUBSPOT_CONFIG };

  if (!currentConfig && pipelines.length > 0) {
    const first = pipelines[0];
    config = {
      ...config,
      default_pipeline_id: first.id,
      default_pipeline_name: first.label,
      default_stage_id: first.stages[0]?.id || "",
      default_stage_name: first.stages[0]?.label || "",
    };
  }

  return {
    pipelines,
    schemas: {
      deals: schemaBundle.dealSchema,
      ...(schemaBundle.contactSchema ? { contacts: schemaBundle.contactSchema } : {}),
      ...(schemaBundle.companySchema ? { companies: schemaBundle.companySchema } : {}),
      ...(lineItemSchema ? { line_items: lineItemSchema } : {}),
    },
    config,
    lineItemsScopeMissing,
    lineItemsSchemaError,
  };
}
