import { crmApi, type CRMConfiguration, type CRMSchema, type Pipeline } from "@/lib/api/crm";

export type SalesforceSetup = {
  pipelines: Pipeline[];
  dealSchema: CRMSchema | null;
  config: CRMConfiguration;
};

export const DEFAULT_SALESFORCE_CONFIG: CRMConfiguration = {
  default_pipeline_id: "sf_opportunity",
  default_pipeline_name: "Opportunity",
  default_stage_id: "",
  default_stage_name: "",
  allowed_deal_fields: ["Name", "Amount", "CloseDate", "StageName", "Description"],
  allowed_contact_fields: ["FirstName", "LastName", "Email", "Phone"],
  allowed_company_fields: ["Name"],
  allowed_line_item_fields: [],
  auto_create_contacts: true,
  auto_create_companies: true,
  auto_sync_hubspot_calls: false,
};

export async function loadSalesforceSetup(): Promise<SalesforceSetup> {
  const [stages, schemaData, currentConfig] = await Promise.all([
    crmApi.getSalesforceStages(),
    crmApi.getSalesforceSchema(),
    crmApi.getSalesforceConfiguration(),
  ]);

  const pipeline: Pipeline = {
    id: "sf_opportunity",
    label: "Opportunity",
    stages: stages.map((s) => ({ id: s.id, label: s.label })),
  };

  let config = currentConfig ?? { ...DEFAULT_SALESFORCE_CONFIG };
  if (!currentConfig && stages.length > 0) {
    config = {
      ...config,
      default_pipeline_id: pipeline.id,
      default_pipeline_name: pipeline.label,
      default_stage_id: stages[0].id,
      default_stage_name: stages[0].label,
    };
  }

  return {
    pipelines: [pipeline],
    dealSchema: schemaData,
    config,
  };
}
