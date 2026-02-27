import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi } from "@/lib/api/crm";
import { memosApi } from "@/features/memos/api";
import { toast } from "sonner";
import { Loader2, Check, AlertCircle, Sparkles, ChevronDown, Search, X, RefreshCw, Pencil, Trash2, Plus } from "lucide-react";

interface HubSpotSyncPreviewProps {
  memoId: string;
  initialDealId?: string | null;
  onSuccess: (data: any) => void;
}

/** Build extraction object from base memo extraction + proposed updates for approve API */
function buildExtractionFromUpdates(
  base: Record<string, unknown>,
  updates: Array<{ field_name: string; field_label?: string; field_type?: string; new_value?: string | number; options?: Array<{ value: string; label?: string }> }>
): Record<string, unknown> {
  const result = { ...base };
  const raw = { ...((result.raw_extraction as Record<string, unknown>) || {}) };

  for (const u of updates) {
    const val = u.new_value != null && u.new_value !== "" ? String(u.new_value).trim() : null;
    if (!val && u.field_name !== "description") continue;

    switch (u.field_name) {
      case "contact_name":
        result.contactName = val;
        break;
      case "company_name":
        result.companyName = val;
        raw.dealname = val;
        break;
      case "dealname":
        result.companyName = val;
        raw.dealname = val;
        break;
      case "amount": {
        const amt = parseFloat(val);
        result.dealAmount = Number.isFinite(amt) ? amt : null;
        raw.amount = result.dealAmount;
        break;
      }
      case "closedate":
        result.closeDate = val;
        raw.closedate = val;
        break;
      case "dealstage":
        result.dealStage = val;
        raw.dealstage = val;
        break;
      case "description":
        result.summary = val || "";
        raw.description = val || "";
        break;
      case "hs_next_step":
        raw.hs_next_step = val;
        result.nextSteps = val ? [val] : [];
        break;
      default:
        if (u.field_name.startsWith("next_step_task_")) {
          const steps = [...((result.nextSteps as string[]) || [])];
          const i = parseInt(u.field_name.replace("next_step_task_", ""), 10);
          if (val && !Number.isNaN(i)) {
            steps[i] = val;
            result.nextSteps = steps.filter(Boolean);
            if ((result.nextSteps as string[])?.[0]) raw.hs_next_step = (result.nextSteps as string[])[0];
          }
        } else if (val) {
          raw[u.field_name] = u.field_type === "number" ? (parseFloat(val) || null) : val;
        }
    }
  }

  return { ...result, raw_extraction: raw };
}

export const HubSpotSyncPreview = ({ memoId, onSuccess, initialDealId }: HubSpotSyncPreviewProps) => {
  const [loading, setLoading] = useState(true);
  const [matching, setMatching] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [extractionError, setExtractionError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [reExtracting, setReExtracting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showSearch, setShowAllSearch] = useState(false);
  const [editedUpdates, setEditedUpdates] = useState<any[] | null>(null);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [showAddField, setShowAddField] = useState(false);

  const fetchPreview = useCallback(
    async (dealId?: string) => {
      setLoading(true);
      try {
        const previewData = await crmApi.getPreview(memoId, dealId);
        setPreview(previewData);
        setEditedUpdates(null);
      } catch {
        toast.error("Failed to load update preview");
      } finally {
        setLoading(false);
      }
    },
    [memoId]
  );

  useEffect(() => {
    const init = async () => {
      setMatching(true);
      setLoading(true);
      try {
        if (initialDealId) {
          await fetchPreview(initialDealId);
          setMatching(false);
          setLoading(false);
          return;
        }
        let matches: any[] = [];
        try {
          const matchData = await crmApi.findMatches(memoId);
          matches = Array.isArray(matchData) ? matchData : [];
        } catch (matchErr: any) {
          const errStr = String(matchErr?.data?.detail ?? "");
          if (matchErr?.status === 400 && errStr.includes("extraction not available")) {
            setExtractionError(true);
            toast.error("Extraction not ready. Please wait for processing or try re-extract.");
            return;
          }
          toast.error("Failed to find matching deals");
        }
        const topDealId = matches.length > 0 ? matches[0].deal_id : undefined;
        await fetchPreview(topDealId);
      } catch (error: any) {
        const errStr = String(error?.data?.detail ?? "");
        if (error?.status === 400 && errStr.includes("extraction not available")) {
          setExtractionError(true);
          toast.error("Extraction not available. Wait for processing or use Re-extract.");
        } else {
          toast.error("Failed to load preview");
        }
        setPreview(null);
      } finally {
        setMatching(false);
        setLoading(false);
      }
    };
    init();
  }, [memoId, retryKey, initialDealId, fetchPreview]);

  const handleReExtract = async () => {
    setReExtracting(true);
    try {
      await memosApi.reExtract(memoId);
      toast.success("Re-extraction started. Loading preview...");
      setExtractionError(false);
      setRetryKey((k) => k + 1);
    } catch (err: any) {
      toast.error(err?.data?.detail || err?.message || "Re-extract failed");
    } finally {
      setReExtracting(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    try {
      const results = await crmApi.searchDeals(searchQuery);
      setSearchResults(results);
    } catch {
      toast.error("Search failed");
    } finally {
      setIsSearching(false);
    }
  };

  const selectDeal = (dealId: string) => {
    fetchPreview(dealId || undefined);
    setShowAllSearch(false);
    setSearchResults([]);
    setSearchQuery("");
  };

  const updates = editedUpdates ?? preview?.proposed_updates ?? [];
  const availableFields = preview?.available_fields ?? [];
  const currentDealId = preview?.selected_deal?.deal_id ?? null;
  const isNewDeal = preview?.is_new_deal ?? true;

  const buildExtractionForSync = async (): Promise<Record<string, unknown> | undefined> => {
    const memo = await memosApi.get(memoId);
    const base = memo?.extraction && typeof memo.extraction === "object" ? { ...memo.extraction } : {};
    const effectiveUpdates = editedUpdates ?? preview?.proposed_updates ?? [];
    if (effectiveUpdates.length === 0) return undefined;
    return buildExtractionFromUpdates(base as Record<string, unknown>, effectiveUpdates);
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const extraction = await buildExtractionForSync();
      const result = await crmApi.approveSync(memoId, currentDealId ?? undefined, isNewDeal, extraction);
      toast.success("CRM updated successfully!");
      onSuccess(result);
    } catch {
      toast.error("Failed to sync with HubSpot");
    } finally {
      setSyncing(false);
    }
  };

  const updateField = (idx: number, newValue: string | number, exitEdit = true) => {
    const list = editedUpdates ?? updates.map((u) => ({ ...u }));
    if (list[idx]) {
      const next = [...list];
      next[idx] = { ...next[idx], new_value: newValue };
      setEditedUpdates(next);
    }
    if (exitEdit) setEditingIdx(null);
  };

  const removeField = (idx: number) => {
    const list = editedUpdates ?? updates.map((u) => ({ ...u }));
    const next = list.slice();
    next[idx] = null;
    setEditedUpdates(next.filter(Boolean));
  };

  const addField = (field: { name: string; label: string; type?: string; options?: unknown[] }) => {
    const newUpdate = {
      field_name: field.name,
      field_label: field.label,
      field_type: field.type || "string",
      current_value: null,
      new_value: "",
      options: field.options,
    };
    const list = editedUpdates ?? updates.map((u) => ({ ...u }));
    setEditedUpdates([...list, newUpdate]);
    setShowAddField(false);
    setEditingIdx(list.length);
  };

  if (extractionError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-6">
        <div className="w-16 h-16 rounded-2xl bg-destructive/10 flex items-center justify-center">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <div className="text-center space-y-2 max-w-sm">
          <p className="text-sm font-black uppercase tracking-widest text-foreground">Extraction Not Available</p>
          <p className="text-xs text-muted-foreground">
            Processing may have failed or is still in progress. If you have a transcript, try Re-extract to run the AI extraction again.
          </p>
          <Button onClick={handleReExtract} disabled={reExtracting} variant="outline" className="mt-6 rounded-full border-beige/40 hover:bg-beige/10">
            {reExtracting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <RefreshCw className="h-4 w-4 mr-2" />}
            {reExtracting ? "Re-extracting..." : "Re-extract"}
          </Button>
        </div>
      </div>
    );
  }

  if (loading && !preview) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-6">
        <div className="relative">
          <Loader2 className="h-12 w-12 animate-spin text-beige" />
          <Sparkles className="absolute -top-2 -right-2 h-5 w-5 text-beige animate-pulse" />
        </div>
        <div className="text-center space-y-2">
          <p className="text-sm font-black uppercase tracking-widest text-foreground">
            {matching ? "Analyzing Transcript..." : "Finding Matching Deal..."}
          </p>
          <p className="text-xs text-muted-foreground max-w-xs mx-auto">Our AI is extracting key details and searching your HubSpot CRM.</p>
        </div>
      </div>
    );
  }

  const dealMatch = preview?.selected_deal;

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between px-2">
        <h5 className={THEME_TOKENS.typography.capsLabel}>Deal Target</h5>
        {!showSearch && (
          <Button variant="ghost" size="sm" onClick={() => setShowAllSearch(true)} className="text-[9px] font-black uppercase tracking-widest text-beige hover:bg-beige/10">
            <Search className="h-3 w-3 mr-1.5" />
            Change Deal
          </Button>
        )}
      </div>

      {showSearch ? (
        <div className="bg-secondary/5 rounded-[2rem] p-6 border-2 border-beige/20 space-y-4">
          <div className="flex items-center gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40" />
              <Input
                placeholder="Search deals by name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                className="bg-white border-border/40 rounded-full pl-11 pr-6 h-11 font-medium text-sm"
              />
            </div>
            <Button onClick={handleSearch} disabled={isSearching} className="bg-beige text-cream rounded-full px-6 h-11 text-[9px] font-black uppercase tracking-widest shrink-0">
              {isSearching ? <Loader2 className="h-3 w-3 animate-spin" /> : "Search"}
            </Button>
            <Button variant="ghost" size="icon" onClick={() => setShowAllSearch(false)} className="rounded-full shrink-0">
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="max-h-[200px] overflow-y-auto space-y-2 pr-2 scrollbar-thin">
            {searchResults.map((deal) => (
              <button
                key={deal.deal_id}
                onClick={() => selectDeal(deal.deal_id)}
                className="w-full text-left p-4 rounded-2xl bg-white border border-border/20 hover:border-beige/40 transition-all flex items-center justify-between group"
              >
                <div className="min-w-0">
                  <p className="text-sm font-bold text-foreground truncate">{deal.deal_name}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[10px] text-muted-foreground uppercase font-black tracking-tight">{deal.stage?.replace(/_/g, " ")}</span>
                    <span className="w-1 h-1 rounded-full bg-border" />
                    <span className="text-[10px] text-muted-foreground/60">{deal.amount || "No amount"}</span>
                  </div>
                </div>
                <div className="w-8 h-8 rounded-full bg-secondary/5 flex items-center justify-center group-hover:bg-beige/10 group-hover:text-beige transition-colors">
                  <ChevronDown className="h-4 w-4 -rotate-90" />
                </div>
              </button>
            ))}
            {searchResults.length === 0 && !isSearching && searchQuery && (
              <div className="text-center py-8">
                <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/40">No matching deals found in HubSpot</p>
              </div>
            )}
          </div>

          <div className="pt-4 border-t border-border/10">
            <button
              onClick={() => selectDeal("")}
              className="w-full py-3 rounded-xl hover:bg-beige/5 text-[9px] font-black uppercase tracking-widest text-muted-foreground/60 hover:text-beige transition-colors text-center"
            >
              + Create a brand new deal
            </button>
          </div>
        </div>
      ) : (
        <div
          className={`p-8 rounded-[2rem] border-2 transition-all duration-500 ${dealMatch ? "bg-success/[0.02] border-success/20" : "bg-beige/[0.02] border-beige/20"}`}
        >
          <div className="flex items-start gap-6">
            <div
              className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-colors duration-500 ${dealMatch ? "bg-success/10 text-success" : "bg-beige/10 text-beige"}`}
            >
              {dealMatch ? <Check className="h-7 w-7" /> : <Sparkles className="h-7 w-7" />}
            </div>
            <div className="flex-1 space-y-1">
              <h4 className="text-xl font-black tracking-tight text-foreground">
                {dealMatch ? "Existing Deal Targeted" : "New Deal Creation"}
              </h4>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {dealMatch ? (
                  <>
                    Targeting <span className="text-foreground font-bold">&quot;{dealMatch.deal_name}&quot;</span>.
                    <span className="block mt-1 text-xs opacity-60 italic">Matched via {dealMatch.match_reason?.toLowerCase()}</span>
                  </>
                ) : (
                  "No existing deal selected. A new record will be created in your primary pipeline."
                )}
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-6">
        <div className="flex items-center justify-between px-2">
          <h5 className={THEME_TOKENS.typography.capsLabel}>Proposed Changes</h5>
          <span className="text-[10px] font-bold text-beige flex items-center gap-1.5">
            <Sparkles className="h-3 w-3" />
            AI Extracted
          </span>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-12 bg-secondary/5 rounded-3xl border border-dashed border-border/40">
            <Loader2 className="h-6 w-6 animate-spin text-beige mb-3" />
            <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/40">Fetching deal details...</p>
          </div>
        ) : updates.length === 0 ? (
          <p className="text-sm text-muted-foreground py-6 text-center">No field updates extracted.</p>
        ) : (
          <div className="grid gap-4">
            {updates.map((update: any, idx: number) => {
              const hadExisting =
                update.current_value != null &&
                String(update.current_value).trim() !== "" &&
                String(update.current_value).trim() !== "(empty)";
              const isOverride = !!hadExisting;
              const isDealField =
                !["contact_name", "company_name"].includes(update.field_name);
              const isEditing = editingIdx === idx;

              return (
                <div
                  key={`${update.field_name}-${idx}`}
                  className={`group relative rounded-3xl p-6 transition-all flex items-start justify-between gap-4 ${
                    isOverride ? "bg-destructive/5 border border-destructive/30 hover:border-destructive/40" : "bg-success/5 border border-success/20 hover:border-success/30"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between mb-2">
                      <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">{update.field_label}</span>
                      {isOverride ? (
                        <span className="bg-destructive/10 text-destructive text-[8px] font-black px-2 py-0.5 rounded-full uppercase tracking-wider shrink-0">Override</span>
                      ) : (
                        <span className="bg-success/10 text-success text-[8px] font-black px-2 py-0.5 rounded-full uppercase tracking-wider shrink-0">New</span>
                      )}
                    </div>
                    {hadExisting && (
                      <p className="text-[10px] text-muted-foreground line-through opacity-50 mb-1">Was: {update.current_value || "—"}</p>
                    )}
                    {isEditing ? (
                      <div className="space-y-2">
                        {update.options && update.options.length > 0 ? (
                          <select
                            autoFocus
                            value={String(update.new_value ?? "")}
                            onChange={(e) => updateField(idx, e.target.value)}
                            className="w-full h-10 rounded-xl border border-border/40 bg-background px-3 text-sm font-medium"
                          >
                            <option value="">—</option>
                            {update.options.map((o: { value: string; label?: string }) => (
                              <option key={o.value} value={o.value}>
                                {o.label ?? o.value}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <Input
                            autoFocus
                            type={update.field_type === "number" ? "number" : update.field_name === "closedate" ? "date" : "text"}
                            value={String(update.new_value ?? "")}
                            onChange={(e) => updateField(idx, e.target.value, false)}
                            onBlur={() => setEditingIdx(null)}
                            onKeyDown={(e) => e.key === "Enter" && setEditingIdx(null)}
                            className="h-10 rounded-xl"
                          />
                        )}
                      </div>
                    ) : (
                      <p className={`text-sm font-bold leading-relaxed ${isOverride ? "text-destructive" : "text-success"}`}>{update.new_value ?? "—"}</p>
                    )}
                  </div>
                  {isDealField && !isEditing && (
                    <div className="flex items-center gap-1 shrink-0">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 rounded-full text-muted-foreground hover:text-beige"
                        onClick={() => setEditingIdx(idx)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 rounded-full text-muted-foreground hover:text-destructive"
                        onClick={() => removeField(idx)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {availableFields.length > 0 && !loading && (
          <div className="relative">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowAddField(!showAddField)}
              className="rounded-full border-beige/40 hover:bg-beige/10 text-[9px] font-black uppercase tracking-widest"
            >
              <Plus className="h-3 w-3 mr-1.5" />
              Add field
            </Button>
            {showAddField && (
              <div className="absolute left-0 top-full mt-2 z-10 w-56 max-h-48 overflow-y-auto py-2 rounded-2xl bg-background border border-border/40 shadow-lg">
                {availableFields
                  .filter((f: { name: string }) => !updates.some((u: any) => u?.field_name === f.name))
                  .map((f: { name: string; label: string; type?: string; options?: unknown[] }) => (
                    <button
                      key={f.name}
                      onClick={() => addField(f)}
                      className="w-full text-left px-4 py-2 text-sm hover:bg-beige/10 transition-colors"
                    >
                      {f.label || f.name}
                    </button>
                  ))}
                {availableFields.filter((f: { name: string }) => !updates.some((u: any) => u?.field_name === f.name)).length === 0 && (
                  <p className="px-4 py-2 text-xs text-muted-foreground">All fields added</p>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {!loading && (
        <div className="p-5 rounded-2xl bg-secondary/5 border border-border/20 flex items-start gap-4">
          <AlertCircle className="h-5 w-5 text-muted-foreground/40 shrink-0 mt-0.5" />
          <p className="text-[10px] text-muted-foreground leading-relaxed">
            AI-suggested values for stages and select fields are automatically mapped to your HubSpot options.
          </p>
        </div>
      )}

      <div className="flex items-center gap-4 pt-6 border-t border-border/40">
        <Button
          variant="hero"
          onClick={handleSync}
          disabled={syncing || loading}
          className="flex-1 bg-beige text-cream hover:bg-beige-dark rounded-full text-[10px] font-black uppercase tracking-widest shadow-large h-14"
        >
          {syncing ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Check className="h-4 w-4 mr-2" />}
          {syncing ? "Syncing..." : dealMatch ? `Update ${dealMatch.deal_name}` : "Create & Sync Deal"}
        </Button>
      </div>
    </div>
  );
};
