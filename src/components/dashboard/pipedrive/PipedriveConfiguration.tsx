import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi, crmKeys, SESSION_QUERY_STALE_MS, type CRMConfiguration } from "@/lib/api/crm";
import {
  DEFAULT_PIPEDRIVE_CONFIG,
  loadPipedriveSetup,
  type PipedriveObjectTab,
} from "@/lib/api/pipedrive-setup";
import { toast } from "sonner";
import { Briefcase, Building2, Check, FilterX, Info, ListChecks, Search, UserPlus, UserRound } from "lucide-react";
import { VocifyLoader } from "@/components/ui/vocify-loader";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Toggle } from "@/components/ui/toggle";
import { SettingsRow, SettingsSection } from "@/components/ui/settings-card";
import {
  CallNoteRows,
  DealsRow,
  FieldsRow,
  ReviewRow,
  SaveStatus,
  useAutosave,
} from "@/components/dashboard/crm/CrmSettingsParts";
import { useLanguage } from "@/lib/i18n";
import { AnimIcon } from "@/components/ui/anim-icon";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

// Sentinel for empty stage selection (no default stage)
const NONE = "__none__";

interface PipedriveConfigurationProps {
  onSaved?: () => void;
  readOnly?: boolean;
}

type ObjectTab = PipedriveObjectTab;

const OBJECT_TABS: { id: ObjectTab; label: string; configKey: keyof CRMConfiguration; icon: typeof Briefcase }[] = [
  { id: "deals", label: "Deal", configKey: "allowed_deal_fields", icon: Briefcase },
  { id: "contacts", label: "Person", configKey: "allowed_contact_fields", icon: UserRound },
  { id: "companies", label: "Organization", configKey: "allowed_company_fields", icon: Building2 },
];

const RECOMMENDED_BY_OBJECT: Record<ObjectTab, string[]> = {
  deals: ["title", "value", "currency", "expected_close_date", "stage_id"],
  contacts: ["name", "emails", "phones"],
  companies: ["name"],
};

export const PipedriveConfiguration = ({ onSaved, readOnly = false }: PipedriveConfigurationProps) => {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: crmKeys.pipedriveSetup(),
    queryFn: loadPipedriveSetup,
    staleTime: SESSION_QUERY_STALE_MS,
  });

  const [draft, setDraft] = useState<CRMConfiguration | null>(null);
  const [activeTab, setActiveTab] = useState<ObjectTab>("deals");
  const [openFields, setOpenFields] = useState<ObjectTab | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAllFields, setShowAllFields] = useState(false);

  const config = draft ?? data?.config ?? DEFAULT_PIPEDRIVE_CONFIG;
  const pipelines = data?.pipelines ?? [];
  const schemas = data?.schemas ?? {};
  const activeConfigKey = OBJECT_TABS.find((t) => t.id === activeTab)!.configKey;
  const selectedFields = (config[activeConfigKey] as string[]) || [];
  const activeSchema = schemas[activeTab];
  const recommended = RECOMMENDED_BY_OBJECT[activeTab];

  const setConfig = (updater: CRMConfiguration | ((prev: CRMConfiguration) => CRMConfiguration)) => {
    setDraft((prev) => {
      const current = prev ?? data?.config ?? DEFAULT_PIPEDRIVE_CONFIG;
      return typeof updater === "function" ? updater(current) : updater;
    });
  };

  const handleRefreshFields = async () => {
    setIsRefreshing(true);
    try {
      const next = await loadPipedriveSetup(true);
      queryClient.setQueryData(crmKeys.pipedriveSetup(), next);
      setDraft(null);
      toast.success("Pipedrive fields updated");
    } catch {
      toast.error("Could not refresh Pipedrive fields");
    } finally {
      setIsRefreshing(false);
    }
  };

  const save = async (next: CRMConfiguration) => {
    await crmApi.savePipedriveConfiguration(next);
    queryClient.setQueryData(crmKeys.pipedriveSetup(), (prev) =>
      prev ? { ...prev, config: next, saved: true } : prev,
    );
    // A change made while this one was saving stays as the draft and saves next.
    setDraft((cur) => (cur === next ? null : cur));
    onSaved?.();
  };
  const saveState = useAutosave(draft, save);

  const filteredProperties = useMemo(() => {
    if (!activeSchema) return [];
    return activeSchema.properties.filter((p) => {
      const matchesSearch =
        p.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.name.toLowerCase().includes(searchQuery.toLowerCase());
      if (searchQuery) return matchesSearch;
      const isRecommended = recommended.includes(p.name);
      const isSelected = selectedFields.includes(p.name);
      return showAllFields || isRecommended || isSelected;
    });
  }, [activeSchema, searchQuery, showAllFields, recommended, selectedFields]);

  if (isLoading) {
    return (
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" label="Loading Pipedrive fields..." />
      </div>
    );
  }

  if (isError && !data) {
    return (
      <p className="text-sm text-muted-foreground">Pipedrive login expired. Disconnect it and connect again.</p>
    );
  }

  const selectedPipeline = pipelines.find((p) => p.id === config.default_pipeline_id) ?? pipelines[0];
  const labelOf = (tab: ObjectTab, name: string) =>
    schemas[tab]?.properties.find((p) => p.name === name)?.label ?? name;
  const openEditor = (tab: ObjectTab) => {
    setActiveTab(tab);
    setSearchQuery("");
    setShowAllFields(false);
    setOpenFields((cur) => (cur === tab ? null : tab));
  };

  const fieldEditor = (
    <div className="space-y-4">
      <div className="flex justify-end">
        {!readOnly && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleRefreshFields}
            disabled={isRefreshing || isLoading}
            title="Pull the latest Pipedrive fields and pipelines"
            className="rounded-full h-8 px-3 text-[12px] border-border/50 text-beige shrink-0"
          >
            <AnimIcon name="refresh" size={14} state={isRefreshing && "busy"} className="mr-1.5" />
            Refresh from Pipedrive
          </Button>
        )}
      </div>
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="relative flex-1">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40" />
                <Input
                  placeholder={`Search ${OBJECT_TABS.find((t) => t.id === activeTab)?.label.toLowerCase()} fields...`}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="bg-secondary/5 border-border/40 rounded-full pl-11 pr-6 h-11 font-medium"
                />
              </div>
              {!searchQuery && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowAllFields(!showAllFields)}
                  className={`rounded-full px-6 h-11 text-[9px] font-medium border-border/50 transition-all ${
                    showAllFields ? "bg-beige/10 border-beige/30 text-beige" : ""
                  }`}
                >
                  {showAllFields ? "Show Recommended Only" : `Show All Fields (${activeSchema?.properties.length ?? 0})`}
                </Button>
              )}
            </div>
            <div className="bg-muted/5 rounded-3xl p-6 border border-border/20">
              <div className="flex items-center gap-2 mb-4">
                <Info className="h-3 w-3 text-muted-foreground/40" />
                <p className="text-[10px] text-muted-foreground font-medium italic">
                  Pipedrive field keys (title, name, emails) are sent to your account.
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
                        const active = selectedFields.includes(prop.name);
                        setConfig((prev) => ({
                          ...prev,
                          [activeConfigKey]: active
                            ? selectedFields.filter((f) => f !== prop.name)
                            : [...selectedFields, prop.name],
                        }));
                      }}
                      className="group h-auto w-full justify-between rounded-2xl px-4 py-3 text-left"
                    >
                      <div className="flex flex-col min-w-0">
                        <span className="text-[12px] font-medium truncate">{prop.label}</span>
                        {recommended.includes(prop.name) && (
                          <span className="text-[8px] font-black uppercase tracking-tighter opacity-30 group-hover:opacity-60">
                            Recommended
                          </span>
                        )}
                      </div>
                      {selectedFields.includes(prop.name) && <Check className="h-3 w-3 shrink-0 ml-2" />}
                    </Toggle>
                  ))
                ) : (
                  <div className="col-span-full py-12 flex flex-col items-center justify-center text-muted-foreground/40">
                    <FilterX className="h-10 w-10 mb-4 opacity-20" />
                    <p className="text-sm font-bold">No matching properties found</p>
                  </div>
                )}
              </div>
            </div>
        </div>
    </div>
  );

  return (
    <div className="space-y-8">
      <SettingsSection label="After a call" action={<SaveStatus state={saveState} />}>
        <ReviewRow
          crmName="Pipedrive"
          autoWrite={Boolean(config.auto_sync_hubspot_calls)}
          disabled={readOnly}
          onAutoWriteChange={(val) => setConfig((prev) => ({ ...prev, auto_sync_hubspot_calls: val }))}
        />
      </SettingsSection>

      <SettingsSection label="What Vocify creates">
        <SettingsRow icon={UserPlus} title="People" description="When none matches, from a name. Email or phone alone is not enough.">
          <Switch
            aria-label="Create people"
            checked={config.auto_create_contacts}
            disabled={readOnly}
            onCheckedChange={(val) => setConfig((prev) => ({ ...prev, auto_create_contacts: val }))}
          />
        </SettingsRow>
        <SettingsRow icon={Building2} title="Organizations" description="When none matches, from the company name">
          <Switch
            aria-label="Create organizations"
            checked={config.auto_create_companies}
            disabled={readOnly}
            onCheckedChange={(val) => setConfig((prev) => ({ ...prev, auto_create_companies: val }))}
          />
        </SettingsRow>
        <SettingsRow icon={ListChecks} title="Tasks" description="From what was agreed on the call, on its deal">
          <Switch
            aria-label="Create tasks"
            checked={config.create_tasks !== false}
            disabled={readOnly}
            onCheckedChange={(val) => setConfig((prev) => ({ ...prev, create_tasks: val }))}
          />
        </SettingsRow>
        <DealsRow
          icon={Briefcase}
          rule={config.deal_creation_rule}
          disabled={readOnly}
          onRuleChange={(rule) => setConfig((prev) => ({ ...prev, deal_creation_rule: rule }))}
        >
        <div className="grid sm:grid-cols-2 gap-3">
              <div className="space-y-2">
                <label className={THEME_TOKENS.typography.capsLabel}>Pipeline</label>
                <Select
                  value={config.default_pipeline_id}
                  disabled={readOnly}
                  onValueChange={(pipelineId) => {
                    const p = pipelines.find((pl) => pl.id === pipelineId);
                    if (!p) return;
                    const stage = p.stages[0];
                    setConfig((prev) => ({
                      ...prev,
                      default_pipeline_id: p.id,
                      default_pipeline_name: p.label,
                      default_stage_id: stage?.id ?? "",
                      default_stage_name: stage?.label ?? "",
                      meeting_booked_pipeline_id: null,
                      meeting_booked_stage_id: null,
                    }));
                  }}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {pipelines.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <label className={THEME_TOKENS.typography.capsLabel}>Stage</label>
                <Select
                  value={config.default_stage_id}
                  disabled={readOnly}
                  onValueChange={(stageId) => {
                    const s = selectedPipeline?.stages.find((st) => st.id === stageId);
                    if (s) {
                      setConfig((prev) => ({
                        ...prev,
                        // The pipeline shown above is the one the stage belongs to, even if it was never picked itself.
                        default_pipeline_id: selectedPipeline?.id ?? prev.default_pipeline_id,
                        default_pipeline_name: selectedPipeline?.label ?? prev.default_pipeline_name,
                        default_stage_id: s.id,
                        default_stage_name: s.label,
                      }));
                    }
                  }}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Pick a stage" />
                  </SelectTrigger>
                  <SelectContent>
                    {selectedPipeline?.stages.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {(!data?.saved || !data.config.default_stage_id) && (
                  <p className="text-xs text-warning">
                    {config.default_stage_id
                      ? "Saving this stage. Until then Vocify cannot create deals in Pipedrive."
                      : "Pick a stage: until then Vocify cannot create deals in Pipedrive."}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <label className={THEME_TOKENS.typography.capsLabel}>{t.product.meetingBookedStage}</label>
                <Select
                  value={config.meeting_booked_stage_id ?? NONE}
                  disabled={readOnly || !selectedPipeline}
                  onValueChange={(value) => {
                    const stageId = value === NONE ? null : value;
                    setConfig((prev) => ({
                      ...prev,
                      meeting_booked_pipeline_id: stageId ? selectedPipeline?.id ?? null : null,
                      meeting_booked_stage_id: stageId,
                    }));
                  }}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder={t.product.meetingBookedStageNone} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>{t.product.meetingBookedStageNone}</SelectItem>
                    {selectedPipeline?.stages.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
        </DealsRow>
      </SettingsSection>

      <SettingsSection label="What Vocify writes">
        <CallNoteRows disabled={readOnly} />
        {OBJECT_TABS.map((tab) => (
          <FieldsRow
            key={tab.id}
            icon={tab.icon}
            label={tab.label}
            names={((config[tab.configKey] as string[]) || []).map((n) => labelOf(tab.id, n))}
            open={openFields === tab.id}
            readOnly={readOnly}
            onToggle={() => openEditor(tab.id)}
          >
            {fieldEditor}
          </FieldsRow>
        ))}
      </SettingsSection>
    </div>
  );
};
