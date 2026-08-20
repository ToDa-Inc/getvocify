import { useState, useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi, Pipeline, CRMSchema, CRMConfiguration } from "@/lib/api/crm";
import { toast } from "sonner";
import { Loader2, Check, ChevronDown, ShieldCheck, Settings2, Search, FilterX, Info, X, Plus, PhoneOff, AlertTriangle, RefreshCw } from "lucide-react";
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
  const [newLostReason, setNewLostReason] = useState("");

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

  const addLostReason = () => {
    const reason = newLostReason.trim();
    if (!reason) return;
    setConfig((prev) => {
      const current = prev.lost_reasons || [];
      if (current.some((r) => r.toLowerCase() === reason.toLowerCase())) return prev;
      return { ...prev, lost_reasons: [...current, reason] };
    });
    setNewLostReason("");
  };

  const removeLostReason = (reason: string) => {
    setConfig((prev) => ({
      ...prev,
      lost_reasons: (prev.lost_reasons || []).filter((r) => r !== reason),
    }));
  };

  // Candidate deal properties for the "closed lost reason" mapping: anything
  // whose name/label mentions lost+reason (EN/ES) - same keyword pairs the
  // backend uses for auto-detection (call_outcome.py), shown first so the
  // dropdown isn't just the raw alphabetical property list.
  const lostReasonPropertyCandidates = useMemo(() => {
    const dealProps = schemas.deals?.properties || [];
    const keywordPairs: [string, string][] = [
      ["lost", "reason"], ["perdid", "motivo"], ["perdid", "razon"], ["perdid", "razón"],
    ];
    const isCandidate = (label: string, name: string) => {
      const l = label.toLowerCase();
      const n = name.toLowerCase();
      return keywordPairs.some(([a, b]) => (l.includes(a) && l.includes(b)) || (n.includes(a) && n.includes(b)));
    };
    const candidates = dealProps.filter((p) => isCandidate(p.label, p.name));
    const rest = dealProps.filter((p) => !isCandidate(p.label, p.name));
    return [...candidates, ...rest];
  }, [schemas.deals]);

  // This account's own live Lead Status options - the ONLY source of
  // values the On Hold / Lost dropdowns below can pick from. Vocify never
  // creates HubSpot properties or options (see call_outcome.py module
  // docstring) - the admin maps an EXISTING value here, or creates one in
  // HubSpot themselves first if nothing fits.
  const hsLeadStatusOptions = useMemo(
    () => schemas.contacts?.properties.find((p) => p.name === "hs_lead_status")?.options || [],
    [schemas.contacts],
  );
  const hsLeadStatusValues = useMemo(
    () => new Set(hsLeadStatusOptions.map((o) => o.value)),
    [hsLeadStatusOptions],
  );
  const lostConfigured = !!config.lost_lead_status_value;
  const lostStale = lostConfigured && !hsLeadStatusValues.has(config.lost_lead_status_value as string);
  const lostReady = lostConfigured && !lostStale;
  const onHoldConfigured = !!config.on_hold_lead_status_value;
  const onHoldStale = onHoldConfigured && !hsLeadStatusValues.has(config.on_hold_lead_status_value as string);
  const onHoldReady = onHoldConfigured && !onHoldStale;
  const outcomeMappingComplete = lostReady && onHoldReady;

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
            a live call, research/ICP only fills when empty. One exception: when a rep marks a call as{" "}
            <strong>Converted / On Hold / Lost</strong> in the extension, Vocify always
            writes the contact's lead status (and, if the call was marked Lost, the
            deal's stage + lost reason) — even if <code className="text-[9px]">hs_lead_status</code>{" "}
            or <code className="text-[9px]">dealstage</code> aren't selected below. That's a deliberate
            rep action, not an AI extraction, so it's never filtered by these lists. See
            "Call Outcome" further down to map which of your own Lead Status values each outcome
            writes, and to configure the Lost reasons themselves.
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

      <div className="space-y-6">
        <div className="flex items-center gap-3 text-beige">
          <PhoneOff className="h-4 w-4" />
          <h4 className="text-[10px] font-black uppercase tracking-widest border-b border-beige/10 pb-1 flex-1">
            Call Outcome
          </h4>
        </div>

        <div className="flex items-start gap-2 px-2">
          <Info className="h-3 w-3 text-muted-foreground/40 mt-0.5 shrink-0" />
          <p className="text-[10px] text-muted-foreground font-medium leading-relaxed">
            Vocify never creates or changes properties in your HubSpot - the mapping below points
            the extension's On Hold / Lost buttons at Lead Status values that already exist in your
            account (or ones you create yourself in HubSpot first). Converted needs no setup - it
            reuses HubSpot's own "Open Deal" status.
          </p>
        </div>

        {/*
          Prominent, can't-miss gate: the On Hold / Lost buttons literally
          don't exist in the extension for this account until both rows
          below resolve to a value that's still valid in the live
          hs_lead_status schema (see compute_call_outcome_availability in
          backend/app/services/hubspot/call_outcome.py) - revalidated here
          with the same schema the extension itself checks, so this card
          never claims "ready" when the extension would actually hide the
          button.
        */}
        <div
          className={`rounded-3xl border p-5 space-y-5 ${
            outcomeMappingComplete
              ? "border-emerald-500/20 bg-emerald-500/5"
              : "border-amber-500/30 bg-amber-500/5"
          }`}
        >
          <div className="flex items-start gap-3">
            {outcomeMappingComplete ? (
              <Check className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
            )}
            <div>
              <p className={`text-xs font-black ${outcomeMappingComplete ? "text-emerald-700" : "text-amber-700"}`}>
                {outcomeMappingComplete
                  ? "On Hold and Lost are mapped and ready"
                  : "On Hold / Lost aren't mapped yet"}
              </p>
              <p className="text-[10px] text-muted-foreground font-medium leading-relaxed mt-1">
                {outcomeMappingComplete
                  ? "Reps see both buttons in the extension. Converted always shows - it needs no mapping."
                  : "Until each row below points at a value, that button won't appear in the extension at all - reps won't know it's missing, they'll just never see it. Map what you can now; anything left unmapped simply stays hidden."}
              </p>
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className={THEME_TOKENS.typography.capsLabel}>"Lost" means</label>
                {lostReady && <Check className="h-3 w-3 text-emerald-600" />}
              </div>
              <div className="relative">
                <select
                  value={config.lost_lead_status_value || ""}
                  onChange={(e) =>
                    setConfig((prev) => ({ ...prev, lost_lead_status_value: e.target.value || null }))
                  }
                  className="w-full h-11 px-5 rounded-full border border-border/40 bg-background text-foreground appearance-none cursor-pointer font-bold text-xs focus:outline-none"
                >
                  <option value="">Not mapped - button hidden</option>
                  {hsLeadStatusOptions.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                  {lostStale && config.lost_lead_status_value && (
                    <option value={config.lost_lead_status_value}>
                      {config.lost_lead_status_value} (no longer exists)
                    </option>
                  )}
                </select>
                <ChevronDown className="absolute right-5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/40 pointer-events-none" />
              </div>
              {lostStale && (
                <p className="text-[9px] text-amber-700 font-bold leading-relaxed px-1">
                  This value was deleted or renamed in HubSpot - pick another one.
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className={THEME_TOKENS.typography.capsLabel}>"On Hold" means</label>
                {onHoldReady && <Check className="h-3 w-3 text-emerald-600" />}
              </div>
              <div className="relative">
                <select
                  value={config.on_hold_lead_status_value || ""}
                  onChange={(e) =>
                    setConfig((prev) => ({ ...prev, on_hold_lead_status_value: e.target.value || null }))
                  }
                  className="w-full h-11 px-5 rounded-full border border-border/40 bg-background text-foreground appearance-none cursor-pointer font-bold text-xs focus:outline-none"
                >
                  <option value="">Not mapped - button hidden</option>
                  {hsLeadStatusOptions.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                  {onHoldStale && config.on_hold_lead_status_value && (
                    <option value={config.on_hold_lead_status_value}>
                      {config.on_hold_lead_status_value} (no longer exists)
                    </option>
                  )}
                </select>
                <ChevronDown className="absolute right-5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/40 pointer-events-none" />
              </div>
              {onHoldStale && (
                <p className="text-[9px] text-amber-700 font-bold leading-relaxed px-1">
                  This value was deleted or renamed in HubSpot - pick another one.
                </p>
              )}
            </div>
          </div>

          {!onHoldConfigured && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-2xl bg-background/60 border border-border/30">
              <Info className="h-3 w-3 text-muted-foreground/40 mt-0.5 shrink-0" />
              <p className="text-[10px] text-muted-foreground font-medium leading-relaxed">
                Don't see anything that fits "on hold"? Most accounts don't - it's rarely a default
                Lead Status. Create one yourself in HubSpot first:{" "}
                <strong>Settings → Properties → Contact properties → Lead Status → Edit → Add option</strong>,
                then come back here and select it.
              </p>
            </div>
          )}
        </div>

        <div className="flex items-start gap-2 px-2">
          <Info className="h-3 w-3 text-muted-foreground/40 mt-0.5 shrink-0" />
          <p className="text-[10px] text-muted-foreground font-medium leading-relaxed">
            Reasons shown in the extension when a rep marks a call as <strong>Lost</strong> — a
            reason is always required for Lost. Reps can also type their own via "Other". The
            reason itself is always recorded as a HubSpot note regardless of the mapping above.
          </p>
        </div>

        <div className="space-y-3">
          <label className={THEME_TOKENS.typography.capsLabel}>Lost Reasons</label>
          <div className="flex flex-wrap gap-2">
            {(config.lost_reasons || []).map((reason) => (
              <span
                key={reason}
                className="flex items-center gap-2 px-4 py-2 rounded-full text-[10px] font-bold bg-beige/10 border border-beige/30 text-beige"
              >
                {reason}
                <button
                  type="button"
                  onClick={() => removeLostReason(reason)}
                  className="opacity-50 hover:opacity-100 transition-opacity"
                  aria-label={`Remove ${reason}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <Input
              placeholder="Add a Lost reason..."
              value={newLostReason}
              onChange={(e) => setNewLostReason(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addLostReason();
                }
              }}
              className="bg-secondary/5 border-border/40 rounded-full px-6 h-11 font-medium flex-1"
            />
            <Button
              type="button"
              variant="outline"
              onClick={addLostReason}
              disabled={!newLostReason.trim()}
              className="rounded-full h-11 px-5 border-border/50"
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="space-y-2">
          <label className={THEME_TOKENS.typography.capsLabel}>
            Deal "Lost Reason" Property
          </label>
          <div className="relative">
            <select
              value={config.lost_reason_deal_property || ""}
              onChange={(e) =>
                setConfig((prev) => ({
                  ...prev,
                  lost_reason_deal_property: e.target.value || null,
                }))
              }
              className="w-full h-12 px-6 rounded-full border border-border/40 bg-secondary/5 text-foreground appearance-none cursor-pointer font-bold focus:outline-none"
            >
              <option value="">Auto-detect (recommended)</option>
              {lostReasonPropertyCandidates.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.label} ({p.name})
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-6 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40 pointer-events-none" />
          </div>
          <div className="flex items-start gap-2 px-2 pt-1">
            <Info className="h-3 w-3 text-muted-foreground/40 mt-0.5 shrink-0" />
            <p className="text-[10px] text-muted-foreground font-medium leading-relaxed">
              Auto-detect looks for a property named <code className="text-[9px]">closed_lost_reason</code>{" "}
              or labeled like a lost reason on every sync, so this works even if you never
              touch this dropdown. Pick a specific property here only to override that.
            </p>
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
