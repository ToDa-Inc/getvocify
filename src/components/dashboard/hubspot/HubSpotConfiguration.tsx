import { useState, useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi, Pipeline, CRMSchema } from "@/lib/api/crm";
import { toast } from "sonner";
import { Loader2, Check, ChevronDown, ShieldCheck, Settings2, Search, FilterX, Info } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";

interface HubSpotConfigurationProps {
  onSaved?: () => void;
}

const RECOMMENDED_FIELDS = [
  'dealname', 'amount', 'description', 'closedate', 'dealstage', 
  'pipeline', 'hs_next_step', 'hs_priority', 'hs_deal_stage_probability'
];

export const HubSpotConfiguration = ({ onSaved }: HubSpotConfigurationProps) => {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [dealSchema, setDealSchema] = useState<CRMSchema | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAllFields, setShowAllFields] = useState(false);

  const [config, setConfig] = useState({
    default_pipeline_id: "",
    default_pipeline_name: "",
    default_stage_id: "",
    default_stage_name: "",
    allowed_deal_fields: ["dealname", "amount", "description", "closedate"],
    allowed_contact_fields: ["firstname", "lastname", "email", "phone"],
    allowed_company_fields: ["name", "domain"],
    auto_create_contacts: true,
    auto_create_companies: true,
  });

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [pipelinesData, schemaData, currentConfig] = await Promise.all([
          crmApi.getPipelines(),
          crmApi.getSchema("deals"),
          crmApi.getConfiguration(),
        ]);

        setPipelines(pipelinesData);
        setDealSchema(schemaData);

        if (currentConfig) {
          setConfig(currentConfig);
        } else if (pipelinesData.length > 0) {
          const firstPipeline = pipelinesData[0];
          setConfig(prev => ({
            ...prev,
            default_pipeline_id: firstPipeline.id,
            default_pipeline_name: firstPipeline.label,
            default_stage_id: firstPipeline.stages[0].id,
            default_stage_name: firstPipeline.stages[0].label,
          }));
        }
      } catch (error) {
        toast.error("Failed to load HubSpot configuration");
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await crmApi.saveConfiguration(config as any);
      toast.success("Configuration saved!");
      onSaved?.();
    } catch (error) {
      toast.error("Failed to save configuration");
    } finally {
      setIsSaving(false);
    }
  };

  const filteredProperties = useMemo(() => {
    if (!dealSchema) return [];
    
    return dealSchema.properties.filter(p => {
      // Filter out system fields that shouldn't be edited directly
      if (['hs_object_id', 'createdate', 'lastmodifieddate'].includes(p.name)) return false;
      
      const matchesSearch = p.label.toLowerCase().includes(searchQuery.toLowerCase()) || 
                           p.name.toLowerCase().includes(searchQuery.toLowerCase());
      
      if (searchQuery) return matchesSearch;

      // If not searching, show either recommended, currently selected, or everything if "showAllFields" is true
      const isRecommended = RECOMMENDED_FIELDS.includes(p.name);
      const isSelected = config.allowed_deal_fields.includes(p.name);
      
      return showAllFields || isRecommended || isSelected;
    });
  }, [dealSchema, searchQuery, showAllFields, config.allowed_deal_fields]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 space-y-4">
        <Loader2 className="h-8 w-8 animate-spin text-beige" />
        <p className={THEME_TOKENS.typography.capsLabel}>Loading Schema...</p>
      </div>
    );
  }

  const selectedPipeline = pipelines.find(p => p.id === config.default_pipeline_id);

  return (
    <div className="space-y-10">
      {/* Pipeline Section */}
      <div className="space-y-6">
        <div className="flex items-center gap-3 text-beige">
          <Settings2 className="h-4 w-4" />
          <h4 className="text-[10px] font-black uppercase tracking-widest border-b border-beige/10 pb-1 flex-1">
            Pipeline Settings
          </h4>
        </div>

        <div className="grid sm:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>Active Pipeline</label>
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
                      default_stage_id: p.stages[0].id,
                      default_stage_name: p.stages[0].label,
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
          </div>

          <div className="space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>Default Stage</label>
            <div className="relative">
              <select
                value={config.default_stage_id}
                onChange={(e) => {
                  const s = selectedPipeline?.stages.find(s => s.id === e.target.value);
                  if (s) {
                    setConfig(prev => ({
                      ...prev,
                      default_stage_id: s.id,
                      default_stage_name: s.label,
                    }));
                  }
                }}
                className="w-full h-12 px-6 rounded-full border border-border/40 bg-secondary/5 text-foreground appearance-none cursor-pointer font-bold focus:outline-none"
              >
                {selectedPipeline?.stages.map(s => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>
              <ChevronDown className="absolute right-6 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40 pointer-events-none" />
            </div>
          </div>
        </div>
      </div>

      {/* Permissions Section */}
      <div className="space-y-6">
        <div className="flex items-center gap-3 text-beige">
          <ShieldCheck className="h-4 w-4" />
          <h4 className="text-[10px] font-black uppercase tracking-widest border-b border-beige/10 pb-1 flex-1">
            Editable Fields
          </h4>
        </div>

        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40" />
              <Input 
                placeholder="Search deal properties..." 
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
                className={`rounded-full px-6 h-11 text-[9px] font-black uppercase tracking-widest border-border/50 transition-all ${
                  showAllFields ? 'bg-beige/10 border-beige/30 text-beige' : ''
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
                {searchQuery 
                  ? `Showing matches for "${searchQuery}"`
                  : showAllFields 
                    ? "Displaying all available HubSpot properties"
                    : "Displaying recommended fields for sales updates"}
              </p>
            </div>
            
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {filteredProperties.length > 0 ? (
                filteredProperties.map(prop => (
                  <button
                    key={prop.name}
                    onClick={() => {
                      const active = config.allowed_deal_fields.includes(prop.name);
                      setConfig(prev => ({
                        ...prev,
                        allowed_deal_fields: active
                          ? prev.allowed_deal_fields.filter(f => f !== prop.name)
                          : [...prev.allowed_deal_fields, prop.name]
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
                        <span className="text-[8px] font-black uppercase tracking-tighter opacity-30 group-hover:opacity-60">Recommended</span>
                      )}
                    </div>
                    {config.allowed_deal_fields.includes(prop.name) && (
                      <Check className="h-3 w-3 shrink-0 ml-2" />
                    )}
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

      {/* Auto-create Section */}
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="flex items-center justify-between p-4 rounded-2xl bg-secondary/5 border border-border/20">
          <div>
            <p className="font-bold text-foreground text-xs">Auto-create Contacts</p>
            <p className="text-[9px] text-muted-foreground mt-0.5 tracking-tight">Create contacts from memo extractions when not found in HubSpot. Requires contact name or email.</p>
          </div>
          <Switch 
            checked={config.auto_create_contacts} 
            onCheckedChange={(val) => setConfig(prev => ({ ...prev, auto_create_contacts: val }))} 
          />
        </div>
        <div className="flex items-center justify-between p-4 rounded-2xl bg-secondary/5 border border-border/20">
          <div>
            <p className="font-bold text-foreground text-xs">Auto-create Companies</p>
            <p className="text-[9px] text-muted-foreground mt-0.5 tracking-tight">Create companies from memo extractions when not found in HubSpot. Requires company name.</p>
          </div>
          <Switch 
            checked={config.auto_create_companies} 
            onCheckedChange={(val) => setConfig(prev => ({ ...prev, auto_create_companies: val }))} 
          />
        </div>
      </div>

      <div className="flex items-center gap-2 px-2">
        <Info className="h-3 w-3 text-muted-foreground/40" />
        <p className="text-[9px] text-muted-foreground font-medium italic">
          When both are off, only deal fields are updated.
        </p>
      </div>

      <Button
        onClick={handleSave}
        disabled={isSaving}
        className="w-full bg-beige text-cream hover:bg-beige-dark rounded-full text-[10px] font-black uppercase tracking-widest shadow-medium h-12"
      >
        {isSaving ? (
          <Loader2 className="h-4 w-4 animate-spin mr-2" />
        ) : null}
        Save Configuration
      </Button>
    </div>
  );
};


