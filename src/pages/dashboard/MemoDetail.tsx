import { useState, useEffect, useCallback, useRef } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Play, Pause, Check, ChevronDown, ExternalLink, Sparkles, AlertCircle, RefreshCw, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { HubSpotSyncPreview } from "@/components/dashboard/hubspot/HubSpotSyncPreview";
import { api } from "@/shared/lib/api-client";
import { memosApi } from "@/features/memos/api";
import { crmApi } from "@/lib/api/crm";
import type { MemoExtraction } from "@/features/memos/types";

/** Parse bullet text (• item\n• item2) or plain lines into string array */
function parseBulletList(text: string): string[] {
  if (!text?.trim()) return [];
  return text
    .split(/\n+/)
    .map((line) => line.replace(/^[•\-*]\s*/, ""))
    .filter((line) => line.trim().length > 0);
}

/** Format string array to bullet list for textarea */
function formatBulletList(items: unknown): string {
  if (!Array.isArray(items) || items.length === 0) return "";
  return items.map((s) => `• ${String(s ?? "")}`).join("\n");
}

/** Human-readable labels for raw_extraction keys */
const RAW_FIELD_LABELS: Record<string, string> = {
  dealname: "Deal Name",
  amount: "Amount",
  closedate: "Close Date",
  description: "Deal Description",
  deal_ftes_active: "Deal FTEs (Active)",
  ftes_fulltime_employees: "FTEs (full-time employees)",
  price_per_fte_eur: "Price per FTE (€)",
  competitor_price: "Competitor price (€)",
  hs_next_step: "Next Step (HubSpot)",
  hs_priority: "Priority",
  es_hi_provider: "ES Hi Provider",
  total_employees: "Total employees",
};
const EXPLICIT_RAW_FIELDS = new Set(Object.keys(RAW_FIELD_LABELS));

const MemoDetail = () => {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const dealIdFromUrl = searchParams.get("deal_id");
  const [memo, setMemo] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audio] = useState(new Audio());
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [syncResult, setSyncResult] = useState<any>(null);
  const [isReExtracting, setIsReExtracting] = useState(false);
  const [isConfirmingTranscript, setIsConfirmingTranscript] = useState(false);
  /** Editable transcript for pending_transcript (before extraction) */
  const [editedTranscript, setEditedTranscript] = useState<string>("");
  /** Wizard step: 1=transcript, 2=fields, 3=preview (prevents preview API until user reaches step 3) */
  const [reviewStep, setReviewStep] = useState(1);

  const mergedDealIdRef = useRef<string | null>(null);
  /** Reset to step 1 when memo id changes; init editedTranscript when transcript available */
  useEffect(() => {
    setReviewStep(1);
    mergedDealIdRef.current = null;
    if (memo?.transcript) setEditedTranscript(memo.transcript);
  }, [id, memo?.transcript]);

  /** Scroll to Step 3 when it appears */
  useEffect(() => {
    if (reviewStep === 3) {
      const el = document.getElementById("step-3-sync");
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [reviewStep]);

  /** Session keep-alive when on step 2/3 to prevent logout during long review */
  useEffect(() => {
    if (reviewStep < 2) return;
    const id = setInterval(() => {
      api.get("/auth/me").catch(() => {});
    }, 90_000);
    return () => clearInterval(id);
  }, [reviewStep]);

  /** Editable extraction state - controlled form, initialized from memo.extraction */
  const [editedExtraction, setEditedExtraction] = useState<MemoExtraction | null>(null);

  /** Initialize edited extraction from memo whenever memo.extraction changes */
  useEffect(() => {
    const ext = memo?.extraction;
    if (ext && typeof ext === "object") {
      try {
        const nextSteps = Array.isArray(ext.nextSteps) ? [...ext.nextSteps] : [];
        const raw = ext.raw_extraction && typeof ext.raw_extraction === "object" ? { ...ext.raw_extraction } : {};
        // Sync hs_next_step from first nextStep when missing (for HubSpot)
        if (nextSteps.length > 0 && !raw.hs_next_step) {
          raw.hs_next_step = nextSteps[0];
        }
        setEditedExtraction({
          companyName: ext.companyName ?? null,
          dealAmount: ext.dealAmount ?? null,
          dealCurrency: ext.dealCurrency ?? "EUR",
          dealStage: ext.dealStage ?? null,
          closeDate: ext.closeDate ?? null,
          contactName: ext.contactName ?? null,
          contactRole: ext.contactRole ?? null,
          contactEmail: ext.contactEmail ?? null,
          contactPhone: ext.contactPhone ?? null,
          summary: ext.summary ?? "",
          painPoints: Array.isArray(ext.painPoints) ? [...ext.painPoints] : [],
          nextSteps,
          competitors: Array.isArray(ext.competitors) ? [...ext.competitors] : [],
          objections: Array.isArray(ext.objections) ? [...ext.objections] : [],
          decisionMakers: Array.isArray(ext.decisionMakers) ? [...ext.decisionMakers] : [],
          confidence: ext.confidence && typeof ext.confidence === "object" ? { ...ext.confidence } : { overall: 0, fields: {} },
          raw_extraction: Object.keys(raw).length ? raw : undefined,
        });
      } catch (e) {
        console.error("Failed to init editedExtraction:", e);
        setEditedExtraction(null);
      }
    } else {
      setEditedExtraction(null);
    }
  }, [memo?.extraction]);

  /** Pre-fill extraction with deal context when opening from HubSpot (?deal_id=) */
  useEffect(() => {
    if (!dealIdFromUrl || !editedExtraction || mergedDealIdRef.current === dealIdFromUrl) return;
    mergedDealIdRef.current = dealIdFromUrl;
    let cancelled = false;
    crmApi.getDealContext(dealIdFromUrl).then((ctx) => {
      if (cancelled || !ctx) return;
      const isEmpty = (v: unknown) =>
        v == null || v === "" || String(v).trim().toLowerCase() === "unknown";
      const next: MemoExtraction = { ...editedExtraction };
      if (isEmpty(next.companyName) && ctx.companyName) next.companyName = ctx.companyName;
      if (isEmpty(next.contactName) && ctx.contactName) next.contactName = ctx.contactName;
      if (isEmpty(next.contactEmail) && ctx.contactEmail) next.contactEmail = ctx.contactEmail;
      const raw = { ...(next.raw_extraction || {}) };
      const r = ctx.raw_extraction || {};
      if (isEmpty(raw.dealname) && r.dealname) raw.dealname = r.dealname as string;
      if ((raw.amount == null || isEmpty(raw.amount)) && r.amount != null) raw.amount = r.amount as number;
      if (isEmpty(raw.closedate) && r.closedate) raw.closedate = r.closedate as string;
      if (isEmpty(raw.dealstage) && r.dealstage) raw.dealstage = r.dealstage as string;
      if (isEmpty(raw.hs_next_step) && r.hs_next_step) raw.hs_next_step = r.hs_next_step as string;
      next.raw_extraction = raw;
      setEditedExtraction(next);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [dealIdFromUrl, editedExtraction]);

  useEffect(() => {
    if (memo?.audioUrl) {
      audio.src = memo.audioUrl;
      audio.load();
    }
  }, [memo?.audioUrl]);

  useEffect(() => {
    const handleTimeUpdate = () => setCurrentTime(audio.currentTime);
    const handleLoadedMetadata = () => setDuration(audio.duration);
    const handleEnded = () => setIsPlaying(false);

    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('loadedmetadata', handleLoadedMetadata);
    audio.addEventListener('ended', handleEnded);

    return () => {
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('loadedmetadata', handleLoadedMetadata);
      audio.removeEventListener('ended', handleEnded);
      audio.pause();
    };
  }, [audio]);

  const togglePlay = () => {
    if (isPlaying) {
      audio.pause();
    } else {
      audio.play().catch(console.error);
    }
    setIsPlaying(!isPlaying);
  };

  const formatDuration = (seconds: number) => {
    if (!seconds) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  useEffect(() => {
    const fetchMemo = async () => {
      if (!id) return;
      try {
        setIsLoading(true);
        const data = await api.get<any>(`/memos/${id}`);
        setMemo(data);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch memo:", err);
        setError("Could not load memo details.");
      } finally {
        setIsLoading(false);
      }
    };

    fetchMemo();
    
    // Poll for updates if it's still processing
    let interval: number | null = null;
    if (memo && ['uploading', 'transcribing', 'extracting', 'pending_transcript'].includes(memo.status)) {
      interval = window.setInterval(fetchMemo, 3000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [id, memo?.status]);

  const handleSyncSuccess = (result: any) => {
    setSyncResult(result);
  };

  const handleReExtract = async () => {
    if (!id) return;
    setIsReExtracting(true);
    try {
      const updated = await memosApi.reExtract(id);
      setMemo(updated);
      toast.success("Re-extraction started. AI is extracting CRM fields...");
    } catch (err: any) {
      toast.error(err?.data?.detail || "Re-extract failed");
    } finally {
      setIsReExtracting(false);
    }
  };

  const handleUpdateExtraction = useCallback((updates: Partial<MemoExtraction>) => {
    setEditedExtraction((prev) => (prev ? { ...prev, ...updates } : null));
  }, []);

  const handleUpdateRawField = useCallback((key: string, value: string | number | null) => {
    setEditedExtraction((prev) => {
      if (!prev) return null;
      const raw = { ...(prev.raw_extraction || {}) };
      if (value === null || value === "" || (typeof value === "number" && isNaN(value))) {
        delete raw[key];
      } else {
        raw[key] = value;
      }
      return { ...prev, raw_extraction: Object.keys(raw).length ? raw : undefined };
    });
  }, []);

  // Early returns - must stay after all hooks
  if (isLoading && !memo) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <div className="w-12 h-12 border-4 border-beige border-t-transparent rounded-full animate-spin" />
        <p className={THEME_TOKENS.typography.capsLabel}>Loading conversation...</p>
      </div>
    );
  }

  if (error || !memo) {
    return (
      <div className="max-w-2xl mx-auto text-center space-y-6 pt-20">
        <div className="w-20 h-20 bg-destructive/10 rounded-full flex items-center justify-center mx-auto">
          <AlertCircle className="h-10 w-10 text-destructive" />
        </div>
        <h2 className="text-2xl font-black tracking-tight">Something went wrong</h2>
        <p className="text-muted-foreground">{error || "Conversation not found."}</p>
        <Button asChild variant="outline" className="rounded-full">
          <Link to="/dashboard/memos">Back to Memos</Link>
        </Button>
      </div>
    );
  }

  const extraction = editedExtraction || memo?.extraction || {};
  const isPendingTranscript = memo.status === "pending_transcript";
  const isProcessing = ['uploading', 'transcribing', 'extracting'].includes(memo.status);
  const extractionFailed = memo.status === "failed";

  if (syncResult) {
    return (
      <div className={`max-w-2xl mx-auto ${THEME_TOKENS.motion.fadeIn} text-center`}>
        <Link 
          to="/dashboard/memos" 
          className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 hover:text-beige mb-12 transition-colors group"
        >
          <ArrowLeft className="h-3 w-3 group-hover:-translate-x-1 transition-transform" />
          Back to Memos
        </Link>
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.container} p-16 relative overflow-hidden group`}>
          <div className="absolute inset-0 bg-gradient-to-br from-success/10 to-transparent" />
          <div className="relative z-10">
            <div className={`w-20 h-20 mx-auto mb-8 ${THEME_TOKENS.radius.card} bg-success/10 flex items-center justify-center`}>
              <Check className="h-10 w-10 text-success shadow-[0_0_15px_rgba(34,197,94,0.3)]" />
            </div>
            <h2 className="text-3xl font-black tracking-tighter text-foreground mb-4">Sync Successful</h2>
            <p className="text-muted-foreground mb-10 leading-relaxed mx-auto max-w-sm">
              Updated deal <span className="text-foreground font-bold">{syncResult.deal_name || extraction.companyName || "Unknown"}</span> in HubSpot. All tasks and associations have been processed.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              {syncResult.deal_url ? (
                <Button variant="hero" size="xl" asChild className="rounded-full bg-beige text-cream px-10 shadow-large hover:scale-105 transition-transform">
                  <a href={syncResult.deal_url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-4 w-4 mr-2" />
                    View in HubSpot
                  </a>
                </Button>
              ) : null}
              <Button variant="ghost" asChild className="rounded-full px-10">
                <Link to="/dashboard/record">Record Another</Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`max-w-6xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
      {/* Back Link */}
      <Link 
        to="/dashboard/memos" 
        className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 hover:text-beige mb-10 transition-colors group"
      >
        <ArrowLeft className="h-3 w-3 group-hover:-translate-x-1 transition-transform" />
        Back to Memos
      </Link>

      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Memo <span className={THEME_TOKENS.typography.accentTitle}>Details</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>
          {isProcessing ? "Step 1: AI is extracting CRM fields..." : extractionFailed ? "Step 1 failed. Re-extract to continue." : "Step 2: Review & approve. Then update to CRM."}
        </p>
      </div>

      {/* Step 1 failed banner - Re-extract to continue */}
      {extractionFailed && (
        <div className="mb-8 p-6 rounded-[2rem] border-2 border-destructive/30 bg-destructive/5 flex flex-col sm:flex-row items-start sm:items-center gap-4">
          <div className="flex items-start gap-4 flex-1">
            <div className="w-12 h-12 rounded-2xl bg-destructive/10 flex items-center justify-center shrink-0">
              <AlertCircle className="h-6 w-6 text-destructive" />
            </div>
            <div>
              <p className="font-bold text-foreground mb-1">Step 1 failed: AI extraction</p>
              <p className="text-sm text-muted-foreground">
                {memo.errorMessage || "Extraction failed. You have a transcript — try Re-extract."}
              </p>
              {memo.errorMessage?.toLowerCase().includes("401") && (
                <p className="text-xs text-muted-foreground mt-2">
                  If your OpenRouter key works when tested, try Re-extract — the error may be from a previous attempt.
                </p>
              )}
            </div>
          </div>
          <Button
            onClick={handleReExtract}
            disabled={isReExtracting}
            variant="outline"
            className="rounded-full border-beige/40 hover:bg-beige/10 shrink-0"
          >
            {isReExtracting ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            {isReExtracting ? "Re-extracting..." : "Re-extract"}
          </Button>
        </div>
      )}

      {/* 3-step flow indicator */}
      <div className="mb-8 grid grid-cols-3 gap-4">
        <div className={`p-4 rounded-2xl border-2 transition-colors ${isProcessing ? 'border-beige/40 bg-beige/5' : extractionFailed ? 'border-muted/30 bg-muted/5' : 'border-success/20 bg-success/5'}`}>
          <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">1</span>
          <p className="font-bold text-foreground mt-1">AI extracts CRM fields</p>
          <p className="text-xs text-muted-foreground mt-0.5">Company, contact, deal amount, next steps</p>
        </div>
        <div className={`p-4 rounded-2xl border-2 transition-colors ${!isProcessing && !extractionFailed && memo.extraction ? 'border-beige/40 bg-beige/5' : 'border-muted/30 bg-muted/5'}`}>
          <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">2</span>
          <p className="font-bold text-foreground mt-1">You review & approve</p>
          <p className="text-xs text-muted-foreground mt-0.5">Edit any fields before syncing</p>
        </div>
        <div className="p-4 rounded-2xl border-2 border-muted/30 bg-muted/5">
          <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">3</span>
          <p className="font-bold text-foreground mt-1">Update to CRM</p>
          <p className="text-xs text-muted-foreground mt-0.5">Deal, contact, tasks sync to HubSpot</p>
        </div>
      </div>

      <div className="grid lg:grid-cols-5 gap-8">
        {/* Left Column - Transcript (Step 1) */}
        <div className={`space-y-6 ${reviewStep === 1 ? "lg:col-span-5" : "lg:col-span-2"}`}>
          {/* Audio Player - only when we have audio (file upload flow) */}
          {memo.audioUrl && (
            <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.card} p-6`}>
              <div className="flex items-center gap-5">
                <Button 
                  variant="outline" 
                  size="icon"
                  onClick={togglePlay}
                  className="rounded-full w-12 h-12 bg-beige text-cream border-none hover:scale-105 transition-transform"
                >
                  {isPlaying ? (
                    <Pause className="h-5 w-5" />
                  ) : (
                    <Play className="h-5 w-5 ml-1" />
                  )}
                </Button>
                <div className="flex-1 space-y-2">
                  <div className="h-1.5 bg-foreground/5 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-beige rounded-full shadow-[0_0_10px_rgba(245,215,176,0.3)] transition-all duration-100" 
                      style={{ width: `${(currentTime / (duration || 1)) * 100}%` }}
                    />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className={`${THEME_TOKENS.typography.capsLabel} !text-foreground/40`}>
                      {Math.floor(currentTime / 60)}:{(Math.floor(currentTime % 60)).toString().padStart(2, '0')}
                    </span>
                    <span className={`${THEME_TOKENS.typography.capsLabel} !text-foreground/40`}>
                      {duration ? `${Math.floor(duration / 60)}:${(Math.floor(duration % 60)).toString().padStart(2, '0')}` : formatDuration(memo.audioDuration)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Transcript */}
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
            <div className="flex items-center justify-between mb-8">
              <h3 className={THEME_TOKENS.typography.capsLabel}>Transcript</h3>
              {memo.transcriptConfidence && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest bg-success/10 text-success">
                  <span className="w-1.5 h-1.5 rounded-full bg-success shadow-[0_0_8px_rgba(34,197,94,0.4)]" />
                  {Math.round(memo.transcriptConfidence * 100)}% accuracy
                </span>
              )}
            </div>
            {memo.transcript ? (
              isPendingTranscript ? (
                <Textarea
                  value={editedTranscript}
                  onChange={(e) => setEditedTranscript(e.target.value)}
                  placeholder="Edit transcript if needed..."
                  className="min-h-[200px] font-mono text-sm"
                  readOnly={false}
                />
              ) : (
                <div className="prose prose-sm text-muted-foreground max-h-[500px] overflow-y-auto pr-4 scrollbar-thin">
                  {memo.transcript.split('\n').map((line: string, i: number) => (
                    <p key={i} className="mb-4 leading-relaxed tracking-tight">{line}</p>
                  ))}
                </div>
              )
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center opacity-40">
                <Sparkles className="h-8 w-8 mb-4 animate-pulse" />
                <p className="text-[10px] font-black uppercase tracking-widest">Generating transcript...</p>
              </div>
            )}
            {reviewStep === 1 && !isProcessing && memo?.transcript && (
              <Button
                variant="hero"
                onClick={async () => {
                  if (isPendingTranscript) {
                    setIsConfirmingTranscript(true);
                    try {
                      await memosApi.confirmTranscript(id!, editedTranscript.trim() || undefined);
                      toast.success("AI is extracting CRM fields...");
                      // Poll until pending_review
                      for (let i = 0; i < 60; i++) {
                        await new Promise((r) => setTimeout(r, 2000));
                        const updated = await memosApi.get(id!);
                        setMemo(updated);
                        if (updated.status === "pending_review") {
                          setReviewStep(2);
                          break;
                        }
                        if (updated.status === "failed") {
                          toast.error(updated.errorMessage || "Extraction failed");
                          break;
                        }
                      }
                    } catch (err: any) {
                      toast.error(err?.data?.detail || "Failed to confirm transcript");
                    } finally {
                      setIsConfirmingTranscript(false);
                    }
                  } else {
                    setReviewStep(2);
                  }
                }}
                disabled={isConfirmingTranscript}
                className="mt-6 w-full rounded-full text-[10px] font-black uppercase tracking-widest bg-beige text-cream"
              >
                {isConfirmingTranscript ? "Extracting..." : "Continue to Step 2 – Edit CRM fields"}
              </Button>
            )}
          </div>
        </div>

        {/* Right Column - Extracted Data (Step 2) - only when reviewStep >= 2 */}
        {reviewStep >= 2 && (
        <div className="lg:col-span-3">
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-10`}>
            <div className="mb-10">
              <h3 className={`${THEME_TOKENS.typography.capsLabel}`}>Step 2: Campos que se actualizarán en el CRM</h3>
              <p className="text-xs text-muted-foreground mt-2">
                Revisa y edita los datos antes de sincronizar. Scroll hacia abajo para el paso 3 (Update CRM).
              </p>
            </div>
            
            {isProcessing ? (
              <div className="space-y-12 py-10 flex flex-col items-center justify-center border border-dashed border-border/40 rounded-[2rem] bg-secondary/[0.02]">
                <div className="relative">
                  <div className="absolute inset-0 rounded-full border-4 border-beige/20 animate-ping" />
                  <Sparkles className="h-12 w-12 text-beige" />
                </div>
                <div className="text-center space-y-2">
                  <p className="text-lg font-bold">AI is working its magic...</p>
                  <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/40">Analyzing your sales conversation</p>
                </div>
              </div>
            ) : (
              <div className="space-y-10">
                <div>
                  <h4 className="text-[10px] font-black uppercase tracking-widest text-beige mb-6 pb-2 border-b border-beige/10">
                    Deal Details
                  </h4>
                  <div className="grid sm:grid-cols-2 gap-6">
                    <div className="space-y-2 sm:col-span-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Deal Name (auto)</label>
                      <p className="text-sm font-bold text-muted-foreground py-2 px-4 rounded-full bg-secondary/5">
                        {(extraction.companyName || "Company")} Deal
                      </p>
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Company</label>
                      <Input
                        value={extraction.companyName ?? ""}
                        onChange={(e) => handleUpdateExtraction({ companyName: e.target.value || null })}
                        className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Deal Amount</label>
                      <Input
                        value={extraction.dealAmount != null ? String(extraction.dealAmount) : ""}
                        onChange={(e) => {
                          const v = e.target.value.trim();
                          handleUpdateExtraction({ dealAmount: v ? parseFloat(v) || null : null });
                        }}
                        placeholder="50000"
                        className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Currency</label>
                      <Input
                        value={extraction.dealCurrency ?? "EUR"}
                        onChange={(e) => handleUpdateExtraction({ dealCurrency: e.target.value || "EUR" })}
                        placeholder="EUR"
                        className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Deal Stage</label>
                      <div className="relative">
                        <select
                          value={extraction.dealStage ?? ""}
                          onChange={(e) => handleUpdateExtraction({ dealStage: e.target.value || null })}
                          className="w-full h-12 px-6 rounded-full border border-border/40 bg-secondary/5 text-foreground appearance-none cursor-pointer font-bold focus:outline-none"
                        >
                          <option value="">Select stage</option>
                          <option value="Discovery">Discovery</option>
                          <option value="Proposal">Proposal</option>
                          <option value="Negotiation">Negotiation</option>
                          <option value="Closed Won">Closed Won</option>
                        </select>
                        <ChevronDown className="absolute right-6 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40 pointer-events-none" />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Close Date</label>
                      <Input
                        type="date"
                        value={extraction.closeDate ?? ""}
                        onChange={(e) => handleUpdateExtraction({ closeDate: e.target.value || null })}
                        className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>FTEs / Employees</label>
                      <Input
                        value={
                          extraction.raw_extraction?.deal_ftes_active != null
                            ? String(extraction.raw_extraction.deal_ftes_active)
                            : extraction.raw_extraction?.ftes_fulltime_employees != null
                              ? String(extraction.raw_extraction.ftes_fulltime_employees)
                              : ""
                        }
                        onChange={(e) => {
                          const v = e.target.value.trim();
                          const num = v ? parseFloat(v) : null;
                          handleUpdateRawField("deal_ftes_active", num);
                          handleUpdateRawField("ftes_fulltime_employees", num);
                        }}
                        placeholder="750"
                        className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Price per FTE (€)</label>
                      <Input
                        value={
                          extraction.raw_extraction?.price_per_fte_eur != null
                            ? String(extraction.raw_extraction.price_per_fte_eur)
                            : ""
                        }
                        onChange={(e) => {
                          const v = e.target.value.trim();
                          handleUpdateRawField("price_per_fte_eur", v ? parseFloat(v) || null : null);
                        }}
                        placeholder="3"
                        className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Competitor price (€/emp)</label>
                      <Input
                        value={
                          extraction.raw_extraction?.competitor_price != null
                            ? String(extraction.raw_extraction.competitor_price)
                            : ""
                        }
                        onChange={(e) => {
                          const v = e.target.value.trim();
                          const n = v ? parseFloat(v) : NaN;
                          handleUpdateRawField("competitor_price", v && !isNaN(n) ? n : null);
                        }}
                        placeholder="3"
                        className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Priority</label>
                      <div className="relative">
                        <select
                          value={extraction.raw_extraction?.hs_priority ?? ""}
                          onChange={(e) => handleUpdateRawField("hs_priority", e.target.value || null)}
                          className="w-full h-12 px-6 rounded-full border border-border/40 bg-secondary/5 text-foreground appearance-none cursor-pointer font-bold focus:outline-none"
                        >
                          <option value="">Select priority</option>
                          <option value="high">High</option>
                          <option value="medium">Medium</option>
                          <option value="low">Low</option>
                        </select>
                        <ChevronDown className="absolute right-6 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40 pointer-events-none" />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>ES Hi Provider</label>
                      <Input
                        value={extraction.raw_extraction?.es_hi_provider ?? ""}
                        onChange={(e) => handleUpdateRawField("es_hi_provider", e.target.value.trim() === "" ? null : e.target.value)}
                        placeholder="Adeslas"
                        className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Total employees</label>
                      <Input
                        value={
                          extraction.raw_extraction?.total_employees != null
                            ? String(extraction.raw_extraction.total_employees)
                            : ""
                        }
                        onChange={(e) => {
                          const v = e.target.value.trim();
                          const n = v ? parseFloat(v) : null;
                          handleUpdateRawField("total_employees", n !== null && !isNaN(n) ? n : null);
                        }}
                        placeholder="750"
                        className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
                      />
                    </div>
                  </div>
                </div>

                {/* Additional CRM fields (dynamic - any other raw_extraction keys) */}
                {(() => {
                  const raw = extraction.raw_extraction || {};
                  const EXCLUDED_FROM_ADDITIONAL = new Set([
                    "dealname", "amount", "closedate", "description", "summary", "confidence", "deal_currency_code",
                    "nextSteps", "objections", "painPoints", "competitors", "decisionMakers", "hs_next_step",
                  ]);
                  const otherKeys = Object.keys(raw).filter(
                    (k) =>
                      !EXPLICIT_RAW_FIELDS.has(k) &&
                      !EXCLUDED_FROM_ADDITIONAL.has(k) &&
                      raw[k] != null &&
                      raw[k] !== ""
                  );
                  if (otherKeys.length === 0) return null;
                  return (
                    <div>
                      <h4 className="text-[10px] font-black uppercase tracking-widest text-beige mb-6 pb-2 border-b border-beige/10">
                        Additional CRM Fields
                      </h4>
                      <div className="grid sm:grid-cols-2 gap-6">
                        {otherKeys.map((key) => {
                          const val = raw[key];
                          const label = RAW_FIELD_LABELS[key] || key.replace(/_/g, " ");
                          const isNum = typeof val === "number";
                          return (
                            <div key={key} className="space-y-2">
                              <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>{label}</label>
                              <Input
                                value={String(val ?? "")}
                                onChange={(e) => {
                                  const v = e.target.value;
                                  if (isNum) {
                                    const t = v.trim();
                                    const n = t ? parseFloat(t) : NaN;
                                    handleUpdateRawField(key, t && !isNaN(n) ? n : null);
                                  } else {
                                    handleUpdateRawField(key, v.trim() === "" ? null : v);
                                  }
                                }}
                                className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
                              />
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })()}

                {/* Contact */}
                <div>
                  <h4 className="text-[10px] font-black uppercase tracking-widest text-beige mb-6 pb-2 border-b border-beige/10">
                    Contact Person
                  </h4>
                  <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-6">
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Name</label>
                      <Input
                        value={extraction.contactName ?? ""}
                        onChange={(e) => handleUpdateExtraction({ contactName: e.target.value || null })}
                        className="bg-secondary/5 border-border/40 rounded-full px-4 h-11 font-bold"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Role</label>
                      <Input
                        value={extraction.contactRole ?? ""}
                        onChange={(e) => handleUpdateExtraction({ contactRole: e.target.value || null })}
                        className="bg-secondary/5 border-border/40 rounded-full px-4 h-11 font-bold text-xs"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Email</label>
                      <Input
                        value={extraction.contactEmail ?? ""}
                        onChange={(e) => handleUpdateExtraction({ contactEmail: e.target.value || null })}
                        className="bg-secondary/5 border-border/40 rounded-full px-4 h-11 font-bold text-xs"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Phone</label>
                      <Input
                        value={extraction.contactPhone ?? ""}
                        onChange={(e) => handleUpdateExtraction({ contactPhone: e.target.value || null })}
                        placeholder="+34 600 000 000"
                        className="bg-secondary/5 border-border/40 rounded-full px-4 h-11 font-bold text-xs"
                      />
                    </div>
                  </div>
                </div>

                {/* Summary / Deal Description */}
                <div>
                  <h4 className="text-[10px] font-black uppercase tracking-widest text-beige mb-6 pb-2 border-b border-beige/10">
                    Deal Description / Meeting Summary
                  </h4>
                  <div className="space-y-2">
                    <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Summary</label>
                    <Textarea
                      value={extraction.summary ?? ""}
                      onChange={(e) => handleUpdateExtraction({ summary: e.target.value })}
                      rows={3}
                        placeholder="Meeting summary..."
                      className="bg-secondary/5 border-border/40 rounded-[1.5rem] px-6 py-4 font-medium leading-relaxed"
                    />
                  </div>
                </div>

                {/* Meeting Notes */}
                <div>
                  <h4 className="text-[10px] font-black uppercase tracking-widest text-beige mb-6 pb-2 border-b border-beige/10">
                    Insights & Next Steps
                  </h4>
                  <div className="space-y-6">
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Pain Points</label>
                      <Textarea
                        value={formatBulletList(extraction.painPoints ?? [])}
                        onChange={(e) => handleUpdateExtraction({ painPoints: parseBulletList(e.target.value) })}
                        rows={3}
                        placeholder="• One per line"
                        className="bg-secondary/5 border-border/40 rounded-[1.5rem] px-6 py-4 font-medium leading-relaxed"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Next Steps</label>
                      <Textarea
                        value={formatBulletList(extraction.nextSteps ?? [])}
                        onChange={(e) => {
                          const steps = parseBulletList(e.target.value);
                          handleUpdateExtraction({ nextSteps: steps });
                          // Sync first step to hs_next_step for HubSpot
                          const first = steps.length > 0 ? steps[0] : null;
                          handleUpdateRawField("hs_next_step", first);
                        }}
                        rows={3}
                        placeholder="• One per line"
                        className="bg-secondary/5 border-border/40 rounded-[1.5rem] px-6 py-4 font-medium leading-relaxed"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Competitors</label>
                      <Textarea
                        value={formatBulletList(extraction.competitors ?? [])}
                        onChange={(e) => handleUpdateExtraction({ competitors: parseBulletList(e.target.value) })}
                        rows={2}
                        placeholder="• One per line"
                        className="bg-secondary/5 border-border/40 rounded-[1.5rem] px-6 py-4 font-medium leading-relaxed"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Objections</label>
                      <Textarea
                        value={formatBulletList(extraction.objections ?? [])}
                        onChange={(e) => handleUpdateExtraction({ objections: parseBulletList(e.target.value) })}
                        rows={2}
                        placeholder="• One per line"
                        className="bg-secondary/5 border-border/40 rounded-[1.5rem] px-6 py-4 font-medium leading-relaxed"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Decision Makers</label>
                      <Textarea
                        value={formatBulletList(extraction.decisionMakers ?? [])}
                        onChange={(e) => handleUpdateExtraction({ decisionMakers: parseBulletList(e.target.value) })}
                        rows={2}
                        placeholder="• One per line"
                        className="bg-secondary/5 border-border/40 rounded-[1.5rem] px-6 py-4 font-medium leading-relaxed"
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex items-center justify-between gap-4 mt-12 pt-10 border-t border-border/40">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setReviewStep(1)}
                className="rounded-full px-6 h-11 text-[10px] font-black uppercase tracking-widest text-muted-foreground hover:text-foreground"
              >
                ← Back to Step 1
              </Button>
              <div className="flex items-center gap-3">
                <button type="button" className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/30 hover:text-destructive transition-colors px-6">
                  Reject Memo
                </button>
                {reviewStep === 2 && (
                  <Button
                    type="button"
                    variant="hero"
                    onClick={() => setReviewStep(3)}
                    className="rounded-full px-8 h-12 text-[10px] font-black uppercase tracking-widest bg-beige text-cream shadow-large"
                  >
                    Continue to Step 3 – Update CRM
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
        )}
      </div>

      {/* Step 3: Update to CRM - only mounts when reviewStep 3 (delays preview API call) */}
      {reviewStep === 3 && !isProcessing && !extractionFailed && memo?.extraction && (
        <div id="step-3-sync" className="mt-12">
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-10`}>
            <div className="flex items-center justify-between gap-4 mb-6">
              <h3 className={`${THEME_TOKENS.typography.capsLabel} mb-0`}>Step 3: Review & sync to HubSpot</h3>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setReviewStep(2)}
                className="rounded-full text-[10px] font-black uppercase tracking-widest text-muted-foreground hover:text-foreground"
              >
                ← Back to Step 2
              </Button>
            </div>
            <p className="text-xs text-muted-foreground mb-8">
              Review the deal target and proposed changes below. Click &quot;Update CRM Fields&quot; when ready.
            </p>
            <HubSpotSyncPreview
              memoId={id || ""}
              extraction={editedExtraction}
              initialDealId={dealIdFromUrl}
              onSuccess={handleSyncSuccess}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default MemoDetail;
