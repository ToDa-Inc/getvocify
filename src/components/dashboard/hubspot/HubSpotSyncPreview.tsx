import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi } from "@/lib/api/crm";
import { toast } from "sonner";
import { Loader2, Check, AlertCircle, Sparkles, ChevronDown, ExternalLink, Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";

interface HubSpotSyncPreviewProps {
  memoId: string;
  onSuccess: (data: any) => void;
}

export const HubSpotSyncPreview = ({ memoId, onSuccess }: HubSpotSyncPreviewProps) => {
  const [loading, setLoading] = useState(true);
  const [matching, setMatching] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showSearch, setShowAllSearch] = useState(false);

  const fetchPreview = async (dealId?: string) => {
    setLoading(true);
    try {
      const previewData = await crmApi.getPreview(memoId, dealId);
      setPreview(previewData);
    } catch (error) {
      toast.error("Failed to load update preview");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const init = async () => {
      setMatching(true);
      try {
        const matches = await crmApi.findMatches(memoId);
        const topDealId = Array.isArray(matches) && matches.length > 0 
          ? matches[0].deal_id 
          : undefined;
        await fetchPreview(topDealId);
      } catch (error) {
        toast.error("Failed to analyze memo for CRM updates");
      } finally {
        setMatching(false);
      }
    };
    init();
  }, [memoId]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    try {
      const results = await crmApi.searchDeals(searchQuery);
      setSearchResults(results);
    } catch (error) {
      toast.error("Search failed");
    } finally {
      setIsSearching(false);
    }
  };

  const selectDeal = (dealId: string) => {
    fetchPreview(dealId);
    setShowAllSearch(false);
    setSearchResults([]);
    setSearchQuery("");
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await crmApi.approveSync(
        memoId,
        preview.selected_deal?.deal_id,
        preview.is_new_deal,
        undefined 
      );
      toast.success("CRM updated successfully!");
      onSuccess(result);
    } catch (error) {
      toast.error("Failed to sync with HubSpot");
    } finally {
      setSyncing(false);
    }
  };

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
          <p className="text-xs text-muted-foreground max-w-xs mx-auto">
            Our AI is extracting key details and searching your HubSpot CRM.
          </p>
        </div>
      </div>
    );
  }

  const dealMatch = preview?.selected_deal;
  const updates = preview?.proposed_updates || [];

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Search Header */}
      <div className="flex items-center justify-between px-2">
        <h5 className={THEME_TOKENS.typography.capsLabel}>Deal Target</h5>
        {!showSearch && (
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => setShowAllSearch(true)}
            className="text-[9px] font-black uppercase tracking-widest text-beige hover:bg-beige/10"
          >
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
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
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
            {searchResults.map(deal => (
              <button
                key={deal.deal_id}
                onClick={() => selectDeal(deal.deal_id)}
                className="w-full text-left p-4 rounded-2xl bg-white border border-border/20 hover:border-beige/40 transition-all flex items-center justify-between group"
              >
                <div className="min-w-0">
                  <p className="text-sm font-bold text-foreground truncate">{deal.deal_name}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[10px] text-muted-foreground uppercase font-black tracking-tight">{deal.stage?.replace(/_/g, ' ')}</span>
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
        <div className={`p-8 rounded-[2rem] border-2 transition-all duration-500 ${dealMatch ? 'bg-success/[0.02] border-success/20' : 'bg-beige/[0.02] border-beige/20'}`}>
          <div className="flex items-start gap-6">
            <div className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-colors duration-500 ${dealMatch ? 'bg-success/10 text-success' : 'bg-beige/10 text-beige'}`}>
              {dealMatch ? <Check className="h-7 w-7" /> : <Sparkles className="h-7 w-7" />}
            </div>
            <div className="flex-1 space-y-1">
              <h4 className="text-xl font-black tracking-tight text-foreground">
                {dealMatch ? "Existing Deal Targeted" : "New Deal Creation"}
              </h4>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {dealMatch 
                  ? (
                    <>
                      Targeting <span className="text-foreground font-bold">"{dealMatch.deal_name}"</span>. 
                      <span className="block mt-1 text-xs opacity-60 italic">Matched via {dealMatch.match_reason.toLowerCase()}</span>
                    </>
                  )
                  : "No existing deal selected. A new record will be created in your primary pipeline."}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Proposed Changes */}
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
        ) : (
          <div className="grid gap-4">
            {updates.map((update: any) => {
              const isChanged = update.current_value !== null && update.current_value !== update.new_value;

              return (
                <div 
                  key={update.field_name}
                  className="group relative bg-secondary/5 border border-border/20 rounded-3xl p-6 transition-all hover:border-beige/20"
                >
                  <div className="flex items-start justify-between mb-4">
                    <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">
                      {update.field_label}
                    </span>
                    {isChanged && (
                      <span className="bg-success/10 text-success text-[8px] font-black px-2 py-0.5 rounded-full uppercase tracking-wider">
                        Changed
                      </span>
                    )}
                  </div>

                  <div className="space-y-3">
                    {update.current_value !== null && (
                      <div className="flex items-center gap-3">
                        <span className="text-[10px] text-muted-foreground line-through opacity-50 truncate max-w-[150px]">
                          {update.current_value || "—"}
                        </span>
                        <div className="h-px w-4 bg-muted-foreground/20" />
                      </div>
                    )}
                    <p className="text-sm font-bold text-foreground leading-relaxed">
                      {update.new_value || "—"}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Note for Select Options */}
      {!loading && (
        <div className="p-5 rounded-2xl bg-secondary/5 border border-border/20 flex items-start gap-4">
          <AlertCircle className="h-5 w-5 text-muted-foreground/40 shrink-0 mt-0.5" />
          <p className="text-[10px] text-muted-foreground leading-relaxed">
            AI-suggested values for stages and select fields are automatically mapped to your HubSpot options.
          </p>
        </div>
      )}

      {/* Action Footer */}
      <div className="flex items-center gap-4 pt-6 border-t border-border/40">
        <Button
          variant="hero"
          onClick={handleSync}
          disabled={syncing || loading}
          className="flex-1 bg-beige text-cream hover:bg-beige-dark rounded-full text-[10px] font-black uppercase tracking-widest shadow-large h-14"
        >
          {syncing ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <Check className="h-4 w-4 mr-2" />
          )}
          {syncing ? "Syncing..." : dealMatch ? `Update ${dealMatch.deal_name}` : "Create & Sync Deal"}
        </Button>
      </div>
    </div>
  );
};

