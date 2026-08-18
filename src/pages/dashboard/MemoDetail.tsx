import { useState, useEffect } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Play, Pause, Check, ExternalLink, Sparkles, AlertCircle, RefreshCw, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { HubSpotSyncPreview } from "@/components/dashboard/hubspot/HubSpotSyncPreview";
import { TranscriptConversation } from "@/components/dashboard/memos/TranscriptConversation";
import { api } from "@/shared/lib/api-client";
import { memosApi } from "@/features/memos/api";

/** Infer CRM from sync result URL (HubSpot vs Salesforce REST patterns). */
function formatStageMs(ms: number): string {
  if (!Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

const STAGE_LABELS: Record<string, string> = {
  stt: "Speech-to-text",
  sanitize: "Transcript repair",
  extract: "CRM note + fields",
};

function PipelineMetaCard({ meta }: { meta: any }) {
  const stages = Array.isArray(meta?.stages) ? meta.stages : [];
  if (!stages.length) return null;
  return (
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
      <div className="flex items-center justify-between mb-6">
        <h3 className={THEME_TOKENS.typography.capsLabel}>Pipeline</h3>
        {typeof meta.total_ms === "number" && (
          <span className={`${THEME_TOKENS.typography.capsLabel} !text-foreground/40`}>
            {formatStageMs(meta.total_ms)} total
          </span>
        )}
      </div>
      <div className="space-y-4">
        {stages.map((stage: any, i: number) => (
          <details key={`${stage.name}-${stage.at || i}`} className="group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm">
              <span className="font-medium text-foreground">
                {STAGE_LABELS[stage.name] || stage.name}
              </span>
              <span className="text-muted-foreground tabular-nums">
                {formatStageMs(Number(stage.ms))}
                {stage.model ? ` · ${stage.model}` : ""}
                {stage.error ? " · failed" : ""}
              </span>
            </summary>
            <div className="mt-3 space-y-3 text-xs text-muted-foreground">
              {stage.note && <p>{stage.note}</p>}
              {stage.language && <p>Language: {stage.language}</p>}
              {stage.error && <p className="text-destructive">{stage.error}</p>}
              {(stage.prompts || []).map((prompt: any, pi: number) => (
                <pre
                  key={pi}
                  className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-secondary/40 p-3 font-mono text-[11px] leading-relaxed text-foreground/80"
                >
                  {prompt.role?.toUpperCase()}: {prompt.content || ""}
                </pre>
              ))}
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}

/** Infer CRM from sync result URL (HubSpot vs Salesforce REST patterns). */
function labelsFromDealUrl(dealUrl: string | undefined | null): {
  crmName: string;
  viewInCrm: string;
} {
  const u = (dealUrl || "").toLowerCase();
  if (u.includes("hubspot.com")) {
    return { crmName: "HubSpot", viewInCrm: "View in HubSpot" };
  }
  if (
    u.includes("/lightning/r/opportunity") ||
    u.includes(".salesforce.com") ||
    u.includes(".force.com") ||
    u.includes(".my.salesforce.com")
  ) {
    return { crmName: "Salesforce", viewInCrm: "View in Salesforce" };
  }
  return { crmName: "your CRM", viewInCrm: "View in CRM" };
}

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
  const [reviewContactName, setReviewContactName] = useState<string | null>(null);

  /** Session keep-alive when extraction exists (long review sessions) */
  useEffect(() => {
    if (!memo?.extraction) return;
    const interval = setInterval(() => {
      api.get("/auth/me").catch(() => {});
    }, 90_000);
    return () => clearInterval(interval);
  }, [memo?.extraction]);

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

    audio.addEventListener("timeupdate", handleTimeUpdate);
    audio.addEventListener("loadedmetadata", handleLoadedMetadata);
    audio.addEventListener("ended", handleEnded);

    return () => {
      audio.removeEventListener("timeupdate", handleTimeUpdate);
      audio.removeEventListener("loadedmetadata", handleLoadedMetadata);
      audio.removeEventListener("ended", handleEnded);
      audio.pause();
    };
  }, [audio]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setMemo(null);
    setSyncResult(null);
    setError(null);
    const load = async () => {
      try {
        setIsLoading(true);
        const data = await api.get<any>(`/memos/${id}`);
        if (!cancelled) { setMemo(data); setError(null); }
      } catch (err) {
        console.error("Failed to fetch memo:", err);
        if (!cancelled) setError("Could not load memo details.");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [id]);

  useEffect(() => {
    if (!id || !memo) return;
    const TRANSIENT = ["uploading", "transcribing", "extracting"];
    if (!TRANSIENT.includes(memo.status)) return;

    let cancelled = false;
    const poll = async () => {
      try {
        const data = await api.get<any>(`/memos/${id}`);
        if (cancelled) return;
        setMemo(data);
      } catch { /* silent — next tick retries */ }
    };
    const interval = window.setInterval(poll, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [id, memo?.status]);

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
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const handleSyncSuccess = (result: any) => setSyncResult(result);

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

  const handleConfirmTranscript = async () => {
    if (!id) return;
    setIsConfirmingTranscript(true);
    try {
      await memosApi.confirmTranscript(id);
      toast.success("AI is extracting CRM fields...");
      setMemo((prev: any) => prev ? { ...prev, status: "extracting" } : prev);
    } catch (err: any) {
      toast.error(err?.data?.detail || "Failed to confirm transcript");
    } finally {
      setIsConfirmingTranscript(false);
    }
  };

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

  const isPendingTranscript = memo.status === "pending_transcript";
  const isProcessing = ["uploading", "transcribing", "extracting"].includes(memo.status);
  const extractionFailed = memo.status === "failed";
  const hasExtraction = !isProcessing && !extractionFailed && !!memo.extraction;
  const extraction = memo.extraction || {};

  if (syncResult) {
    const { crmName, viewInCrm } = labelsFromDealUrl(syncResult.deal_url);
    return (
      <div className={`max-w-2xl mx-auto ${THEME_TOKENS.motion.fadeIn} text-center`}>
        <Link
          to="/dashboard/memos"
          className="inline-flex items-center gap-2 text-[10px] font-medium text-muted-foreground/60 hover:text-beige mb-12 transition-colors group"
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
              Updated{" "}
              {crmName === "Salesforce" ? "opportunity" : "deal"}{" "}
              <span className="text-foreground font-bold">{syncResult.deal_name || extraction.companyName || "Unknown"}</span>{" "}
              in {crmName}
              {crmName === "HubSpot" ? ". All tasks and associations have been processed." : "."}
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              {syncResult.deal_url ? (
                <Button variant="hero" size="xl" asChild className="rounded-full bg-beige text-cream px-10 shadow-large hover:opacity-90 transition-opacity">
                  <a href={syncResult.deal_url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-4 w-4 mr-2" />
                    {viewInCrm}
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
      <Link
        to="/dashboard/memos"
        className="inline-flex items-center gap-2 text-[10px] font-medium text-muted-foreground/60 hover:text-beige mb-10 transition-colors group"
      >
        <ArrowLeft className="h-3 w-3 group-hover:-translate-x-1 transition-transform" />
        Back to Memos
      </Link>

      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Memo <span className={THEME_TOKENS.typography.accentTitle}>Details</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>
          {isProcessing
            ? "AI is extracting CRM fields..."
            : extractionFailed
              ? "Extraction failed. Re-extract to continue."
              : "Review and sync to CRM."}
        </p>
      </div>

      {extractionFailed && (
        <div className="mb-8 p-6 rounded-[2rem] border-2 border-destructive/30 bg-destructive/5 flex flex-col sm:flex-row items-start sm:items-center gap-4">
          <div className="flex items-start gap-4 flex-1">
            <div className="w-12 h-12 rounded-2xl bg-destructive/10 flex items-center justify-center shrink-0">
              <AlertCircle className="h-6 w-6 text-destructive" />
            </div>
            <div>
              <p className="font-bold text-foreground mb-1">AI extraction failed</p>
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

      <div className={`grid gap-8 ${hasExtraction ? "lg:grid-cols-5" : ""}`}>
        {/* Left: Transcript (full width when pending/extracting, col-span-2 when has extraction) */}
        <div className={`space-y-6 ${hasExtraction ? "lg:col-span-2" : ""}`}>
          {memo.audioUrl && (
            <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.card} p-6`}>
              <div className="flex items-center gap-5">
                <Button
                  variant="outline"
                  size="icon"
                  onClick={togglePlay}
                  className="rounded-full w-12 h-12 bg-beige text-cream border-none hover:opacity-90 transition-opacity"
                >
                  {isPlaying ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5 ml-1" />}
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
                      {Math.floor(currentTime / 60)}:{(Math.floor(currentTime % 60)).toString().padStart(2, "0")}
                    </span>
                    <span className={`${THEME_TOKENS.typography.capsLabel} !text-foreground/40`}>
                      {duration ? `${Math.floor(duration / 60)}:${(Math.floor(duration % 60)).toString().padStart(2, "0")}` : formatDuration(memo.audioDuration)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
            <div className="flex items-center justify-between mb-8">
              <h3 className={THEME_TOKENS.typography.capsLabel}>Transcript</h3>
              {memo.transcriptConfidence && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[9px] font-medium bg-success/10 text-success">
                  <span className="w-1.5 h-1.5 rounded-full bg-success shadow-[0_0_8px_rgba(34,197,94,0.4)]" />
                  {Math.round(memo.transcriptConfidence * 100)}% accuracy
                </span>
              )}
            </div>
            {memo.transcript ? (
                <TranscriptConversation
                  transcript={memo.transcript}
                  contactName={reviewContactName || extraction.contactName}
                />
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center opacity-40">
                <Sparkles className="h-8 w-8 mb-4 animate-pulse" />
                <p className="text-[10px] font-medium">Generating transcript...</p>
              </div>
            )}
            {isPendingTranscript && !isProcessing && memo?.transcript && (
              <Button
                variant="hero"
                onClick={handleConfirmTranscript}
                disabled={isConfirmingTranscript}
                className="mt-6 w-full rounded-full text-[10px] font-medium bg-beige text-cream"
              >
                {isConfirmingTranscript ? "Extracting..." : "Extract & Continue"}
              </Button>
            )}
          </div>

          {memo.pipelineMeta?.stages?.length ? (
            <PipelineMetaCard meta={memo.pipelineMeta} />
          ) : null}
        </div>

        {/* Right: HubSpotSyncPreview (only when extraction ready) */}
        {hasExtraction && (
          <div className="lg:col-span-3">
            <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-10`}>
              <HubSpotSyncPreview
                memoId={id || ""}
                initialDealId={dealIdFromUrl}
                onSuccess={handleSyncSuccess}
                onContactName={setReviewContactName}
              />
            </div>
          </div>
        )}

        {/* Full-width extracting spinner when no extraction yet */}
        {isProcessing && memo?.transcript && !hasExtraction && (
          <div className="col-span-full flex flex-col items-center justify-center py-16 border border-dashed border-border/40 rounded-[2rem] bg-secondary/[0.02]">
            <div className="relative">
              <div className="absolute inset-0 rounded-full border-4 border-beige/20 animate-ping" />
              <Sparkles className="h-12 w-12 text-beige" />
            </div>
            <p className="mt-6 text-lg font-bold">AI is analyzing your sales conversation</p>
            <p className="text-[10px] font-medium text-muted-foreground/40 mt-1">
              Extracting CRM fields...
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default MemoDetail;
