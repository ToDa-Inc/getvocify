import { crmApi, type CRMConfiguration, type CRMSchema, type Pipeline } from "@/lib/api/crm";

export type PipedriveSetup = {
  pipelines: Pipeline[];
  dealSchema: CRMSchema | null;
  config: CRMConfiguration;
};

export const DEFAULT_PIPEDRIVE_CONFIG: CRMConfiguration = {
  default_pipeline_id: "",
  default_pipeline_name: "",
  default_stage_id: "",
  default_stage_name: "",
  allowed_deal_fields: ["title", "value", "currency", "expected_close_date", "stage_id"],
  allowed_contact_fields: ["name", "emails", "phones"],
  allowed_company_fields: ["name"],
  allowed_line_item_fields: [],
  auto_create_contacts: true,
  auto_create_companies: true,
  auto_sync_hubspot_calls: false,
};

export async function loadPipedriveSetup(refresh = false): Promise<PipedriveSetup> {
  const [pipelines, schemaData, currentConfig] = await Promise.all([
    crmApi.getPipedrivePipelines(),
    crmApi.getPipedriveSchema("deals", refresh ? { refresh: true } : undefined),
    crmApi.getPipedriveConfiguration(),
  ]);

  let config = currentConfig ?? { ...DEFAULT_PIPEDRIVE_CONFIG };
  if (!currentConfig && pipelines.length > 0) {
    const first = pipelines[0];
    const firstStage = first.stages[0];
    config = {
      ...config,
      default_pipeline_id: first.id,
      default_pipeline_name: first.label,
      default_stage_id: firstStage?.id ?? "",
      default_stage_name: firstStage?.label ?? "",
    };
  }

  return {
    pipelines,
    dealSchema: schemaData,
    config,
  };
}
