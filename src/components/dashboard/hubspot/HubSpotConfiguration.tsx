import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi, crmKeys, SESSION_QUERY_STALE_MS, type CRMConfiguration } from "@/lib/api/crm";
import { DEFAULT_HUBSPOT_CONFIG, loadHubSpotSetup, type HubSpotObjectTab } from "@/lib/api/hubspot-setup";
import { toast } from "sonner";
import { Check, Search, FilterX, Info } from "lucide-react";
import { VocifyLoader, VocifySpinner } from "@/components/ui/vocify-loader";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import { Toggle } from "@/components/ui/toggle";
import { classifyFillPolicy, FILL_POLICY_LABELS, type FillPolicy } from "@/lib/fill-policy";
import { AutoAcceptCrmToggle } from "@/components/dashboard/crm/AutoAcceptCrmToggle";
import { DealCreationRuleField } from "@/components/dashboard/crm/DealCreationRuleField";
import { useLanguage } from "@/lib/i18n";
import { AnimIcon } from "@/components/ui/anim-icon";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";

// Sentinel for empty stage selection (no default stage)
const NONE = "__none__";

interface HubSpotConfigurationProps {
  onSaved?: () => void;
  readOnly?: boolean;
}

type ObjectTab = HubSpotObjectTab;

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

export const HubSpotConfiguration = ({ onSaved, readOnly = false }: HubSpotConfigurationProps) => {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: crmKeys.hubspotSetup(),
    queryFn: () => loadHubSpotSetup(false),
    staleTime: SESSION_QUERY_STALE_MS,
  });

  const [draft, setDraft] = useState<CRMConfiguration | null>(null);
  const [activeTab, setActiveTab] = useState<ObjectTab>("deals");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAllFields, setShowAllFields] = useState(false);
  const [fieldView, setFieldView] = useState<"mapped" | "recommended" | "all">("mapped");

  const config = draft ?? data?.config ?? DEFAULT_HUBSPOT_CONFIG;
  const pipelines = data?.pipelines ?? [];
  const schemas = data?.schemas ?? {};
  const lineItemsScopeMissing = data?.lineItemsScopeMissing ?? false;
  const lineItemsSchemaError = data?.lineItemsSchemaError ?? false;

  const setConfig = (updater: CRMConfiguration | ((prev: CRMConfiguration) => CRMConfiguration)) => {
    setDraft((prev) => {
      const current = prev ?? data?.config ?? DEFAULT_HUBSPOT_CONFIG;
      return typeof updater === "function" ? updater(current) : updater;
    });
  };

  const handleRefreshFields = async () => {
    setIsRefreshing(true);
    try {
      const next = await loadHubSpotSetup(true);
      queryClient.setQueryData(crmKeys.hubspotSetup(), next);
      setDraft(null);
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
      queryClient.setQueryData(crmKeys.hubspotSetup(), (prev) =>
        prev ? { ...prev, config } : prev,
      );
      setDraft(null);
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
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" label="Loading HubSpot fields..." />
      </div>
    );
  }

  if (isError && !data) {
    return (
      <p className="text-sm text-muted-foreground">Could not load HubSpot fields. Try again in a moment.</p>
    );
  }

  const selectedPipeline = pipelines.find((p) => p.id === config.default_pipeline_id);

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <h4 className={THEME_TOKENS.typography.capsLabel}>New deals</h4>
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="space-y-1.5 min-w-0">
            <span className="block text-[13px] text-foreground">Pipeline</span>
            {pipelines.length > 1 ? (
              <Select
                value={config.default_pipeline_id}
                disabled={readOnly}
                onValueChange={(pipelineId) => {
                  const p = pipelines.find(p => p.id === pipelineId);
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
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {pipelines.map(p => (
                    <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="h-10 px-4 rounded-full border border-border/40 bg-secondary/5 flex items-center text-sm text-foreground">
                {config.default_pipeline_name || "Sales pipeline"}
              </div>
            )}
          </label>

          <label className="space-y-1.5 min-w-0">
            <span className="block text-[13px] text-foreground">If the call has no stage</span>
            <Select
              value={config.default_stage_id}
              disabled={readOnly}
              onValueChange={(stageId) => {
                const s = selectedPipeline?.stages.find((st) => st.id === stageId);
                if (s) {
                  setConfig((prev) => ({
                    ...prev,
                    default_stage_id: s.id,
                    default_stage_name: s.label,
                  }));
                }
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {selectedPipeline?.stages.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>

          <label className="space-y-1.5 min-w-0">
            <span className="block text-[13px] text-foreground">{t.product.meetingBookedStage}</span>
            <Select
              value={config.meeting_booked_stage_id ?? NONE}
              disabled={readOnly || pipelines.length === 0}
              onValueChange={(value) => {
                const stageId = value === NONE ? null : value;
                // The stage where reps mark a booked meeting may live in any pipeline (an outbound
                // BDR board), not only the one new deals go to.
                const owner = stageId ? pipelines.find((pl) => pl.stages.some((st) => st.id === stageId)) : undefined;
                setConfig((prev) => ({
                  ...prev,
                  meeting_booked_pipeline_id: owner?.id ?? null,
                  meeting_booked_stage_id: stageId,
                }));
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t.product.meetingBookedStageNone} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{t.product.meetingBookedStageNone}</SelectItem>
                {pipelines.length > 1
                  ? pipelines.map((pl) => (
                      <SelectGroup key={pl.id}>
                        <SelectLabel>{pl.label}</SelectLabel>
                        {pl.stages.map((s) => (
                          <SelectItem key={s.id} value={s.id}>
                            {s.label}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    ))
                  : selectedPipeline?.stages.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        {s.label}
                      </SelectItem>
                    ))}
              </SelectContent>
            </Select>
          </label>
        </div>
      </div>

      <DealCreationRuleField
        value={config.deal_creation_rule}
        disabled={readOnly}
        onChange={(rule) => setConfig((prev) => ({ ...prev, deal_creation_rule: rule }))}
      />

      <AutoAcceptCrmToggle
        checked={Boolean(config.auto_sync_hubspot_calls)}
        disabled={readOnly}
        onCheckedChange={(val) => setConfig((prev) => ({ ...prev, auto_sync_hubspot_calls: val }))}
      />

      {(lineItemsScopeMissing || lineItemsSchemaError) && (
        <div className="rounded-2xl border border-warning/30 bg-warning/5 px-5 py-4 text-sm text-foreground">
          <p className="font-bold mb-1">
            {lineItemsScopeMissing
              ? "HubSpot needs a reconnect for line items"
              : "Couldn't load HubSpot line item fields"}
          </p>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {lineItemsScopeMissing
              ? "Your current HubSpot grant is missing line-item scopes. Token refresh cannot add them — open Integrations in Settings and refresh HubSpot permissions. This keeps your saved configuration and sync history."
              : "Deals/contacts still work. Retry later, or reconnect HubSpot from Integrations if this keeps happening."}
          </p>
        </div>
      )}

      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <h4 className={`${THEME_TOKENS.typography.capsLabel} flex-1`}>Fields AI can fill</h4>
          {!readOnly && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleRefreshFields}
            disabled={isRefreshing || isLoading}
            title="Pull the latest HubSpot properties and pipelines"
            className="rounded-full h-8 px-3 text-[12px] border-border/50 text-beige shrink-0"
          >
            <AnimIcon name="refresh" size={14} state={isRefreshing && "busy"} className="mr-1.5" />
            Refresh
          </Button>
          )}
        </div>

        <Segmented<HubSpotObjectTab>
          aria-label="Object"
          value={activeTab}
          onValueChange={(tab) => {
            setActiveTab(tab);
            setSearchQuery("");
            setShowAllFields(false);
            setFieldView("mapped");
          }}
          className="flex-wrap"
          options={OBJECT_TABS.map((tab) => ({
            value: tab.id,
            label: (
              <>
                {tab.label}
                <span className="opacity-50">{((config[tab.configKey] as string[]) || []).length}</span>
              </>
            ),
          }))}
        />

        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="relative min-w-[12rem] flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40" />
              <Input
                placeholder={`Search ${activeTab.replace("_", " ")} properties...`}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-secondary/5 border-border/40 rounded-full pl-11 pr-6 h-11 font-medium"
              />
            </div>
            {!searchQuery && activeSchema && (
              <Segmented<"mapped" | "recommended" | "all">
                aria-label="Fields"
                value={fieldView}
                onValueChange={(mode) => {
                  setFieldView(mode);
                  setShowAllFields(mode === "all");
                }}
                options={[
                  { value: "mapped", label: `Mapped (${selectedFields.length})` },
                  { value: "recommended", label: "Recommended" },
                  { value: "all", label: `All fields (${activeSchema.properties.length})` },
                ]}
              />
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
                  <Toggle
                    key={prop.name}
                    variant="chip"
                    pressed={selectedFields.includes(prop.name)}
                    onPressedChange={() => {
                      if (readOnly) return;
                      toggleField(prop.name);
                    }}
                    className={`group h-auto w-full justify-between rounded-2xl px-4 py-3 text-left ${readOnly ? "cursor-default" : ""}`}
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
                  </Toggle>
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

      <div className="grid sm:grid-cols-2 gap-3">
        <div className="flex items-start gap-4 p-3.5 rounded-2xl bg-secondary/5 border border-border/20">
          <div className="min-w-0 flex-1">
            <p className="text-[13px] text-foreground">Create contacts</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              If none match, create from name or email.
            </p>
          </div>
          <Switch
            className="shrink-0 mt-0.5"
            checked={config.auto_create_contacts}
            disabled={readOnly}
            onCheckedChange={(val) => setConfig((prev) => ({ ...prev, auto_create_contacts: val }))}
          />
        </div>
        <div className="flex items-start gap-4 p-3.5 rounded-2xl bg-secondary/5 border border-border/20">
          <div className="min-w-0 flex-1">
            <p className="text-[13px] text-foreground">Create companies</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              If none match, create from company name.
            </p>
          </div>
          <Switch
            className="shrink-0 mt-0.5"
            checked={config.auto_create_companies}
            disabled={readOnly}
            onCheckedChange={(val) => setConfig((prev) => ({ ...prev, auto_create_companies: val }))}
          />
        </div>
      </div>

      {!readOnly && (
      <Button
        onClick={handleSave}
        disabled={isSaving}
        className="w-full bg-beige text-cream hover:bg-beige/90 rounded-full text-[10px] font-medium shadow-medium h-12"
      >
        {isSaving ? <VocifySpinner size={12} /> : null}
        Save Configuration
      </Button>
      )}
    </div>
  );
};
