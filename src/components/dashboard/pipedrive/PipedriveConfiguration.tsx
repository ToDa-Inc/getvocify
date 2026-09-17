import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi, crmKeys, SESSION_QUERY_STALE_MS, type CRMConfiguration } from "@/lib/api/crm";
import { DEFAULT_PIPEDRIVE_CONFIG, loadPipedriveSetup } from "@/lib/api/pipedrive-setup";
import { toast } from "sonner";
import { Check, ChevronDown, ShieldCheck, Settings2, Search, FilterX, Info, RefreshCw } from "lucide-react";
import { VocifyLoader, VocifySpinner } from "@/components/ui/vocify-loader";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { AutoAcceptCrmToggle } from "@/components/dashboard/crm/AutoAcceptCrmToggle";

interface PipedriveConfigurationProps {
  onSaved?: () => void;
  readOnly?: boolean;
}

const RECOMMENDED_FIELDS = ["title", "value", "currency", "expected_close_date", "stage_id"];

export const PipedriveConfiguration = ({ onSaved, readOnly = false }: PipedriveConfigurationProps) => {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: crmKeys.pipedriveSetup(),
    queryFn: loadPipedriveSetup,
    staleTime: SESSION_QUERY_STALE_MS,
  });

  const [draft, setDraft] = useState<CRMConfiguration | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAllFields, setShowAllFields] = useState(false);

  const config = draft ?? data?.config ?? DEFAULT_PIPEDRIVE_CONFIG;
  const pipelines = data?.pipelines ?? [];
  const dealSchema = data?.dealSchema ?? null;

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
      toast.success("Pipedrive fields updated. Enable new properties below, then Save.");
    } catch {
      toast.error("Could not refresh Pipedrive fields");
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await crmApi.savePipedriveConfiguration(config);
      queryClient.setQueryData(crmKeys.pipedriveSetup(), (prev) =>
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

  const filteredProperties = useMemo(() => {
    if (!dealSchema) return [];
    return dealSchema.properties.filter((p) => {
      const matchesSearch =
        p.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.name.toLowerCase().includes(searchQuery.toLowerCase());
      if (searchQuery) return matchesSearch;
      const isRecommended = RECOMMENDED_FIELDS.includes(p.name);
      const isSelected = config.allowed_deal_fields.includes(p.name);
      return showAllFields || isRecommended || isSelected;
    });
  }, [dealSchema, searchQuery, showAllFields, config.allowed_deal_fields]);

  if (isLoading) {
    return (
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" label="Loading Pipedrive fields..." />
      </div>
    );
  }

  if (isError && !data) {
    return (
      <p className="text-sm text-muted-foreground">Could not load Pipedrive fields. Try again in a moment.</p>
    );
  }

  const selectedPipeline = pipelines.find((p) => p.id === config.default_pipeline_id) ?? pipelines[0];

  return (
    <div className="space-y-10">
      <div className="space-y-6">
        <div className="flex items-center gap-3 text-beige">
          <Settings2 className="h-4 w-4" />
          <h4 className="text-[10px] font-medium border-b border-beige/10 pb-1 flex-1">
            Default pipeline and stage (new deals)
          </h4>
        </div>
        <div className="grid sm:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>Pipeline</label>
            <div className="relative">
              <select
                value={config.default_pipeline_id}
                disabled={readOnly}
                onChange={(e) => {
                  const p = pipelines.find((pl) => pl.id === e.target.value);
                  if (!p) return;
                  const stage = p.stages[0];
                  setConfig((prev) => ({
                    ...prev,
                    default_pipeline_id: p.id,
                    default_pipeline_name: p.label,
                    default_stage_id: stage?.id ?? "",
                    default_stage_name: stage?.label ?? "",
                  }));
                }}
                className="w-full h-12 px-6 rounded-full border border-border/40 bg-secondary/5 text-foreground appearance-none cursor-pointer font-bold focus:outline-none"
              >
                {pipelines.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-6 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40 pointer-events-none" />
            </div>
          </div>
          <div className="space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>Stage</label>
            <div className="relative">
              <select
                value={config.default_stage_id}
                disabled={readOnly}
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

      <AutoAcceptCrmToggle
        checked={Boolean(config.auto_sync_hubspot_calls)}
        disabled={readOnly}
        onCheckedChange={(val) => setConfig((prev) => ({ ...prev, auto_sync_hubspot_calls: val }))}
      />

      <div className="space-y-6">
        <div className="flex items-center gap-3 text-beige">
          <ShieldCheck className="h-4 w-4" />
          <h4 className="text-[10px] font-medium border-b border-beige/10 pb-1 flex-1">
            Editable fields
          </h4>
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
              {isRefreshing ? <VocifySpinner size={12} /> : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />}
              Refresh
            </Button>
          )}
        </div>
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40" />
              <Input
                placeholder="Search deal fields..."
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
                {showAllFields ? "Show Recommended Only" : `Show All Fields (${dealSchema?.properties.length})`}
              </Button>
            )}
          </div>
          <div className="bg-muted/5 rounded-3xl p-6 border border-border/20">
            <div className="flex items-center gap-2 mb-4">
              <Info className="h-3 w-3 text-muted-foreground/40" />
              <p className="text-[10px] text-muted-foreground font-medium italic">
                Pipedrive field keys (e.g. title, value, stage_id) are sent to your account.
              </p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {filteredProperties.length > 0 ? (
                filteredProperties.map((prop) => (
                  <button
                    key={prop.name}
                    type="button"
                    onClick={() => {
                      if (readOnly) return;
                      const active = config.allowed_deal_fields.includes(prop.name);
                      setConfig((prev) => ({
                        ...prev,
                        allowed_deal_fields: active
                          ? prev.allowed_deal_fields.filter((f) => f !== prop.name)
                          : [...prev.allowed_deal_fields, prop.name],
                      }));
                    }}
                    className={`flex items-center justify-between px-4 py-3 rounded-2xl border transition-all text-left group ${
                      config.allowed_deal_fields.includes(prop.name)
                        ? "bg-beige/10 border-beige/30 text-beige"
                        : "bg-white/50 border-border/20 text-muted-foreground hover:border-border/40"
                    }`}
                  >
                    <div className="flex flex-col min-w-0">
                      <span className="text-[10px] font-bold truncate">{prop.label}</span>
                      {RECOMMENDED_FIELDS.includes(prop.name) && (
                        <span className="text-[8px] font-black uppercase tracking-tighter opacity-30 group-hover:opacity-60">
                          Recommended
                        </span>
                      )}
                    </div>
                    {config.allowed_deal_fields.includes(prop.name) && <Check className="h-3 w-3 shrink-0 ml-2" />}
                  </button>
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

      <div className="grid sm:grid-cols-2 gap-3">
        <div className="flex items-start gap-4 p-3.5 rounded-2xl bg-secondary/5 border border-border/20">
          <div className="min-w-0 flex-1">
            <p className="text-[13px] text-foreground">Create people</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              If none match, create from a name. Email or phone alone is not enough.
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
            <p className="text-[13px] text-foreground">Create organizations</p>
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
        className="w-full bg-beige text-cream hover:bg-beige-dark rounded-full text-[10px] font-medium shadow-medium h-12"
      >
        {isSaving ? <VocifySpinner size={12} /> : null}
        Save Configuration
      </Button>
      )}
    </div>
  );
};
