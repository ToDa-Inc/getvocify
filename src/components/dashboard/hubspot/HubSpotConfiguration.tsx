import { useState, useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi, Pipeline, CRMSchema, CRMConfiguration } from "@/lib/api/crm";
import { toast } from "sonner";
import { Loader2, Check, ChevronDown, ShieldCheck, Settings2, Search, FilterX, Info, RefreshCw } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/shared/lib/api-client";
import { classifyFillPolicy, FILL_POLICY_LABELS, type FillPolicy } from "@/lib/fill-policy";

interface HubSpotConfigurationProps {
  onSaved?: () => void;
}

type ObjectTab = "deals" | "contacts" | "companies" | "line_items";

const OBJECT_TABS: { id: ObjectTab; label: string; configKey: keyof CRMConfiguration }[] = [
  { id: "deals", label: "Deals", configKey: "allowed_deal_fields" },
  { id: "contacts", label: "Contacts", configKey: "allowed_contact_fields" },
  { id: "companies", label: "Companies", configKey: "allowed_company_fields" },
  { id: "line_items", label: "Line items", configKey: "allowed_line_item_fields" },
];

const RECOMMENDED_BY_OBJECT: Record<ObjectTab, string[]> = {
  deals: [
    "dealname", "amount", "description", "closedate", "dealstage",
    "pipeline", "hs_next_step", "hs_priority", "dealtype",
  ],
  contacts: [
    "firstname", "lastname", "email", "phone", "jobtitle",
    "hs_lead_status", "hs_linkedin_url",
  ],
  companies: [
    "name", "domain", "annualrevenue", "numberofemployees", "industry",
  ],
  line_items: ["name", "quantity", "price", "description", "hs_sku"],
};

const SYSTEM_FIELDS = ["hs_object_id", "createdate", "lastmodifieddate", "hs_lastmodifieddate"];

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

export const HubSpotConfiguration = ({ onSaved }: HubSpotConfigurationProps) => {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [schemas, setSchemas] = useState<Partial<Record<ObjectTab, CRMSchema>>>({});
  const [activeTab, setActiveTab] = useState<ObjectTab>("deals");
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAllFields, setShowAllFields] = useState(false);
  const [fieldView, setFieldView] = useState<"mapped" | "recommended" | "all">("mapped");
  const [lineItemsScopeMissing, setLineItemsScopeMissing] = useState(false);
  const [lineItemsSchemaError, setLineItemsSchemaError] = useState(false);

  const [config, setConfig] = useState<CRMConfiguration>({
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
  });

  const applySchemas = (
    dealSchema: CRMSchema,
    contactSchema: CRMSchema | null,
    companySchema: CRMSchema | null,
    lineItemResult: { ok: true; schema: CRMSchema } | { ok: false; err: unknown },
    pipelinesData?: Pipeline[],
  ) => {
    const lineItemSchema = lineItemResult.ok ? lineItemResult.schema : null;
    if (lineItemResult.ok) {
      setLineItemsScopeMissing(false);
      setLineItemsSchemaError(false);
    } else {
      const looksLikeScope = lineItemErrorLooksLikeScope(lineItemResult.err);
      setLineItemsScopeMissing(looksLikeScope);
      setLineItemsSchemaError(!looksLikeScope);
    }
    if (pipelinesData) setPipelines(pipelinesData);
    else if (dealSchema.pipelines?.length) setPipelines(dealSchema.pipelines);
    setSchemas((prev) => ({
      ...prev,
      deals: dealSchema,
      ...(contactSchema ? { contacts: contactSchema } : {}),
      ...(companySchema ? { companies: companySchema } : {}),
      ...(lineItemSchema ? { line_items: lineItemSchema } : {}),
    }));
  };

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [schemaBundle, pipelinesData, currentConfig] = await Promise.all([
          fetchHubSpotSchemas(false),
          crmApi.getPipelines(),
          crmApi.getConfiguration(),
        ]);

        applySchemas(
          schemaBundle.dealSchema,
          schemaBundle.contactSchema,
          schemaBundle.companySchema,
          schemaBundle.lineItemResult,
          pipelinesData,
        );

        if (currentConfig) {
          setConfig({
            ...currentConfig,
            allowed_line_item_fields:
              currentConfig.allowed_line_item_fields?.length
                ? currentConfig.allowed_line_item_fields
                : ["name", "quantity", "price"],
            lost_reasons:
              currentConfig.lost_reasons?.length
                ? currentConfig.lost_reasons
                : ["No budget", "No response", "Chose a competitor", "Bad timing", "Not a fit"],
            lost_reason_deal_property: currentConfig.lost_reason_deal_property ?? null,
            lost_lead_status_value: currentConfig.lost_lead_status_value ?? null,
            on_hold_lead_status_value: currentConfig.on_hold_lead_status_value ?? null,
          });
        } else if (pipelinesData.length > 0) {
          const firstPipeline = pipelinesData[0];
          setConfig((prev) => ({
            ...prev,
            default_pipeline_id: firstPipeline.id,
            default_pipeline_name: firstPipeline.label,
            default_stage_id: firstPipeline.stages[0].id,
            default_stage_name: firstPipeline.stages[0].label,
          }));
        }
      } catch {
        toast.error("Failed to load HubSpot configuration");
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, []);

  const handleRefreshFields = async () => {
    setIsRefreshing(true);
    try {
      const { dealSchema, contactSchema, companySchema, lineItemResult } =
        await fetchHubSpotSchemas(true);
      applySchemas(dealSchema, contactSchema, companySchema, lineItemResult);
      toast.success("HubSpot fields updated. Enable new properties below, then Save.");
    } catch {
      toast.error("Could not refresh HubSpot fields");
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await crmApi.saveConfiguration(config);
      toast.success("Configuration saved!");
      onSaved?.();
    } catch {
      toast.error("Failed to save configuration");
    } finally {
      setIsSaving(false);
    }
  };

  const activeConfigKey = OBJECT_TABS.find((t) => t.id === activeTab)!.configKey;
  const selectedFields = (config[activeConfigKey] as string[]) || [];
  const activeSchema = schemas[activeTab];
  const recommended = RECOMMENDED_BY_OBJECT[activeTab];

  const filteredProperties = useMemo(() => {
    if (!activeSchema) return [];

    const rows = activeSchema.properties.filter((p) => {
      if (SYSTEM_FIELDS.includes(p.name)) return false;

      const matchesSearch =
        p.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.name.toLowerCase().includes(searchQuery.toLowerCase());

      if (searchQuery) return matchesSearch;

      const isRecommended = recommended.includes(p.name);
      const isSelected = selectedFields.includes(p.name);
      if (fieldView === "mapped") return isSelected;
      if (fieldView === "recommended") return isRecommended || isSelected;
      return showAllFields || isRecommended || isSelected;
    });

    return [...rows].sort((a, b) => {
      const aSel = selectedFields.includes(a.name) ? 0 : 1;
      const bSel = selectedFields.includes(b.name) ? 0 : 1;
      if (aSel !== bSel) return aSel - bSel;
      return a.label.localeCompare(b.label);
    });
  }, [activeSchema, searchQuery, showAllFields, selectedFields, recommended, fieldView]);

  const toggleField = (name: string) => {
    setConfig((prev) => {
      const current = (prev[activeConfigKey] as string[]) || [];
      const active = current.includes(name);
      return {
        ...prev,
        [activeConfigKey]: active
          ? current.filter((f) => f !== name)
          : [...current, name],
      };
    });
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 space-y-4">
        <Loader2 className="h-8 w-8 animate-spin text-beige" />
        <p className={THEME_TOKENS.typography.capsLabel}>Loading Schema...</p>
      </div>
    );
  }

  const selectedPipeline = pipelines.find((p) => p.id === config.default_pipeline_id);

  return (
    <div className="space-y-10">
      <div className="space-y-6">
        <div className="flex items-center gap-3 text-beige">
          <Settings2 className="h-4 w-4" />
          <h4 className="text-[10px] font-medium border-b border-beige/10 pb-1 flex-1">
            New Deal Placement
          </h4>
        </div>

        <div className="flex items-start gap-2 px-2">
          <Info className="h-3 w-3 text-muted-foreground/40 mt-0.5 shrink-0" />
          <p className="text-[10px] text-muted-foreground font-medium leading-relaxed">
            Vocify reads each memo and picks the deal stage itself (e.g. a demo booked
            → appointment stage), showing it front and center in the approval screen so
            you can change it before anything is saved — you don't need to set that here.
            The only thing to choose below is which <strong>pipeline</strong> brand-new
            deals go into. If you only have one pipeline in HubSpot, there's nothing to
            do — it already points there. The "Fallback Stage" is just a safety net for
            the rare memo that gives no signal at all about where the deal stands.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>Pipeline for New Deals</label>
            {pipelines.length > 1 ? (
              <div className="relative">
                <select
                  value={config.default_pipeline_id}
                  onChange={(e) => {
                    const p = pipelines.find(p => p.id === e.target.value);
                    if (p) {
                      setConfig(prev => ({
                        ...prev,
                        default_pipeline_id: p.id,
                        default_pipeline_name: p.label,
                        default_stage_id: p.stages[0]?.id || "",
                        default_stage_name: p.stages[0]?.label || "",
                      }));
                    }
                  }}
                  className="w-full h-12 px-6 rounded-full border border-border/40 bg-secondary/5 text-foreground appearance-none cursor-pointer font-bold focus:outline-none"
                >
                  {pipelines.map(p => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-6 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40 pointer-events-none" />
              </div>
            ) : (
              <div className="h-12 px-6 rounded-full border border-border/40 bg-secondary/5 flex items-center font-bold text-foreground">
                {config.default_pipeline_name || "Sales pipeline"}
              </div>
            )}
          </div>

          <div className="space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>Fallback Stage (rarely used)</label>
            <div className="relative">
              <select
                value={config.default_stage_id}
                onChange={(e) => {
                  const s = selectedPipeline?.stages.find((st) => st.id === e.target.value);
                  if (s) {
                    setConfig((prev) => ({
                      ...prev,
                      default_stage_id: s.id,
                      default_stage_name: s.label,
                    }));
                  }
                }}
                className="w-full h-12 px-6 rounded-full border border-border/40 bg-secondary/5 text-foreground appearance-none cursor-pointer font-bold focus:outline-none"
              >
                {selectedPipeline?.stages.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-6 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40 pointer-events-none" />
            </div>
          </div>
        </div>
      </div>

      {(lineItemsScopeMissing || lineItemsSchemaError) && (
        <div className="rounded-2xl border border-warning/30 bg-warning/5 px-5 py-4 text-sm text-foreground">
          <p className="font-bold mb-1">
            {lineItemsScopeMissing
              ? "HubSpot needs a reconnect for line items"
              : "Couldn't load HubSpot line item fields"}
          </p>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {lineItemsScopeMissing
              ? "Your current HubSpot grant is missing line-item scopes. Token refresh cannot add them — go to Integrations and click the shield icon next to HubSpot (\"Refresh permissions\") to re-authorize with line items included. This keeps your saved configuration and sync history; disconnecting would delete both."
              : "Deals/contacts still work. Retry later, or reconnect HubSpot from Integrations if this keeps happening."}
          </p>
        </div>
      )}

      <div className="space-y-6">
        <div className="flex items-center gap-3 text-beige">
          <ShieldCheck className="h-4 w-4" />
          <h4 className="text-[10px] font-medium border-b border-beige/10 pb-1 flex-1">
            Field mapping
          </h4>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleRefreshFields}
            disabled={isRefreshing || isLoading}
            title="Pull the latest HubSpot properties and pipelines"
            className="rounded-full h-8 px-3 text-[9px] font-medium border-border/50 text-beige shrink-0"
          >
            {isRefreshing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            )}
            Refresh from HubSpot
          </Button>
        </div>

        <div className="flex items-start gap-2 px-2">
          <Info className="h-3 w-3 text-muted-foreground/40 mt-0.5 shrink-0" />
          <p className="text-[10px] text-muted-foreground font-medium leading-relaxed">
            Select the HubSpot properties AI may fill from a call. Only selected fields
            are extracted and shown in review. Badges show how each field is treated:
            identity stays on the existing record, pre-call fields are never written from
            a live call, research/ICP only fills when empty.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {OBJECT_TABS.map((tab) => {
            const count = ((config[tab.configKey] as string[]) || []).length;
            const hasSchema = !!schemas[tab.id];
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setActiveTab(tab.id);
                  setSearchQuery("");
                  setShowAllFields(false);
                  setFieldView("mapped");
                }}
                className={`px-4 py-2 rounded-full text-[9px] font-medium border transition-all ${
                  activeTab === tab.id
                    ? "bg-beige/15 border-beige/40 text-beige"
                    : "bg-secondary/5 border-border/30 text-muted-foreground hover:border-border/50"
                } ${!hasSchema && tab.id === "line_items" ? "opacity-60" : ""}`}
              >
                {tab.label}
                <span className="ml-2 opacity-50">{count}</span>
              </button>
            );
          })}
        </div>

        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40" />
              <Input
                placeholder={`Search ${activeTab.replace("_", " ")} properties...`}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-secondary/5 border-border/40 rounded-full pl-11 pr-6 h-11 font-medium"
              />
            </div>
            {!searchQuery && activeSchema && (
              <div className="flex flex-wrap gap-2">
                {(["mapped", "recommended", "all"] as const).map((mode) => (
                  <Button
                    key={mode}
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setFieldView(mode);
                      setShowAllFields(mode === "all");
                    }}
                    className={`rounded-full px-4 h-11 text-[9px] font-medium border-border/50 transition-all ${
                      fieldView === mode ? "bg-beige/10 border-beige/30 text-beige" : ""
                    }`}
                  >
                    {mode === "mapped"
                      ? `Mapped (${selectedFields.length})`
                      : mode === "recommended"
                        ? "Recommended"
                        : `All fields (${activeSchema.properties.length})`}
                  </Button>
                ))}
              </div>
            )}
          </div>

          <div className="bg-muted/5 rounded-3xl p-6 border border-border/20">
            <div className="flex items-center gap-2 mb-4">
              <Info className="h-3 w-3 text-muted-foreground/40" />
              <p className="text-[10px] text-muted-foreground font-medium italic">
                {!activeSchema
                  ? activeTab === "line_items"
                    ? "Line item schema unavailable — reconnect HubSpot with line item scopes, or save defaults."
                    : "Schema unavailable for this object."
                  : searchQuery
                    ? `Showing matches for "${searchQuery}"`
                    : fieldView === "all" || showAllFields
                      ? `Displaying all available ${activeTab.replace("_", " ")} properties`
                      : fieldView === "mapped"
                        ? `Mapped ${activeTab.replace("_", " ")} fields — AI extracts only these`
                        : `Displaying recommended ${activeTab.replace("_", " ")} fields — AI will only write selected ones`}
              </p>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {filteredProperties.length > 0 ? (
                filteredProperties.map((prop) => (
                  <button
                    key={prop.name}
                    type="button"
                    onClick={() => toggleField(prop.name)}
                    className={`flex items-center justify-between px-4 py-3 rounded-2xl border transition-all text-left group ${
                      selectedFields.includes(prop.name)
                        ? "bg-beige/10 border-beige/30 text-beige"
                        : "bg-white/50 border-border/20 text-muted-foreground hover:border-border/40"
                    }`}
                  >
                    <div className="flex flex-col min-w-0">
                      <span className="text-[10px] font-bold truncate">{prop.label}</span>
                      <span className="text-[8px] font-mono opacity-40 truncate">{prop.name}</span>
                      <span className="text-[8px] font-medium uppercase tracking-tighter opacity-50 mt-0.5">
                        {FILL_POLICY_LABELS[classifyFillPolicy(prop as { name: string; label: string; description?: string; fill_policy?: FillPolicy })]}
                      </span>
                      {recommended.includes(prop.name) && (
                        <span className="text-[8px] font-black uppercase tracking-tighter opacity-30 group-hover:opacity-60">
                          Recommended
                        </span>
                      )}
                    </div>
                    {selectedFields.includes(prop.name) && (
                      <Check className="h-3 w-3 shrink-0 ml-2" />
                    )}
                  </button>
                ))
              ) : (
                <div className="col-span-full py-12 flex flex-col items-center justify-center text-muted-foreground/40">
                  <FilterX className="h-10 w-10 mb-4 opacity-20" />
                  <p className="text-sm font-bold">
                    {activeSchema
                      ? fieldView === "mapped" && !searchQuery
                        ? "No fields mapped yet — open Recommended or All to add some"
                        : "No matching properties found"
                      : "No schema loaded"}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <div className="flex items-center justify-between p-4 rounded-2xl bg-secondary/5 border border-border/20">
          <div>
            <p className="font-bold text-foreground text-xs">Auto-create Contacts</p>
            <p className="text-[9px] text-muted-foreground mt-0.5 tracking-tight">
              Create contacts from memo extractions when not found in HubSpot. Requires contact name or email.
            </p>
          </div>
          <Switch
            checked={config.auto_create_contacts}
            onCheckedChange={(val) => setConfig((prev) => ({ ...prev, auto_create_contacts: val }))}
          />
        </div>
        <div className="flex items-center justify-between p-4 rounded-2xl bg-secondary/5 border border-border/20">
          <div>
            <p className="font-bold text-foreground text-xs">Auto-create Companies</p>
            <p className="text-[9px] text-muted-foreground mt-0.5 tracking-tight">
              Create companies from memo extractions when not found in HubSpot. Requires company name.
            </p>
          </div>
          <Switch
            checked={config.auto_create_companies}
            onCheckedChange={(val) => setConfig((prev) => ({ ...prev, auto_create_companies: val }))}
          />
        </div>
      </div>

      <div className="flex items-center gap-2 px-2">
        <Info className="h-3 w-3 text-muted-foreground/40" />
        <p className="text-[9px] text-muted-foreground font-medium italic">
          Selected fields control what AI can extract and write. On existing deals, contact/company
          properties update the associated records; line items are created under the deal.
        </p>
      </div>

      <Button
        onClick={handleSave}
        disabled={isSaving}
        className="w-full bg-beige text-cream hover:bg-beige-dark rounded-full text-[10px] font-medium shadow-medium h-12"
      >
        {isSaving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
        Save Configuration
      </Button>
    </div>
  );
};
