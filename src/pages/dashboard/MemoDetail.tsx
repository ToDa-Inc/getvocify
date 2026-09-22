import { useState, useEffect } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Play, Pause, Check, ExternalLink, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { AuthorLabel } from "@/components/dashboard/AuthorLabel";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { authorChipLabel, canViewCompanyActivity } from "@/lib/activity-authors";
import { HubSpotSyncPreview } from "@/components/dashboard/hubspot/HubSpotSyncPreview";
import { FollowupCard } from "@/components/dashboard/FollowupCard";
import { CoachingScore } from "@/components/dashboard/memos/CoachingScore";
import { InteractionObjections } from "@/components/dashboard/memos/InteractionObjections";
import { MeetingProposalReview } from "@/components/dashboard/memos/MeetingProposalReview";
import { TranscriptConversation } from "@/components/dashboard/memos/TranscriptConversation";
import { memoListSubtitle, memoListTitle } from "@/lib/copilot-note";
import { shouldPollMemo } from "@/lib/memo-poll";
import { VocifyLoader, VocifySpinner } from "@/components/ui/vocify-loader";
import { clearCachedPreview } from "@/lib/preview-cache";
import { api } from "@/shared/lib/api-client";
import { useAuth } from "@/features/auth";
import { memosApi } from "@/features/memos/api";

/** Infer CRM from sync result URL (HubSpot vs Salesforce REST patterns). */
function labelsFromDealUrl(dealUrl: string | undefined | null): {
  crmName: string;
  viewInCrm: string;
} {
  const u = (dealUrl || "").toLowerCase();
  if (u.includes("hubspot.com")) {
    return { crmName: "HubSpot", viewInCrm: "View in HubSpot" };
  }
  if (u.includes("pipedrive.com")) {
    return { crmName: "Pipedrive", viewInCrm: "View in Pipedrive" };
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

function pipedriveCompanyDomain(meta: { company_domain?: string; api_domain?: string } | null | undefined): string | null {
  const fromMeta = (meta?.company_domain || "").trim();
  if (fromMeta) return fromMeta;
  const raw = (meta?.api_domain || "").trim();
  if (!raw) return null;
  try {
    const host = new URL(raw.includes("://") ? raw : `https://${raw}`).hostname.toLowerCase();
    if (!host.endsWith(".pipedrive.com")) return null;
    const sub = host.split(".")[0];
    if (["api", "oauth", "www", "developers", "app"].includes(sub)) return null;
    return sub;
  } catch {
    return null;
  }
}

function pipedriveRecordUrl(
  domain: string | null,
  kind: "deal" | "person",
  recordId: string | null | undefined,
): string | null {
  const id = String(recordId || "").trim();
  if (!domain || !id) return null;
  return `https://${domain}.pipedrive.com/${kind === "person" ? "person" : "deal"}/${id}`;
}

const MemoDetail = () => {
  const { user } = useAuth();
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
  const [crmViewUrl, setCrmViewUrl] = useState<string | null>(null);
  const [isReExtracting, setIsReExtracting] = useState(false);
  const [isReTranscribing, setIsReTranscribing] = useState(false);
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
    setCrmViewUrl(null);
    setReviewContactName(null);
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
    if (!shouldPollMemo(memo)) return;

    let cancelled = false;
    const poll = async () => {
      try {
        const data = await api.get<any>(`/memos/${id}`);
        if (cancelled) return;
        setMemo(data);
      } catch { /* silent — next tick retries */ }
    };
    const interval = window.setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [id, memo?.status, memo?.processedAt, memo?.pipelineMeta, memo?.transcript]);

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

  useEffect(() => {
    const fromResult = syncResult?.deal_url || syncResult?.contact_url || null;
    if (fromResult) {
      setCrmViewUrl(fromResult);
      return;
    }
    const dealId = syncResult?.deal_id || memo?.hubspotDealId || memo?.hubspot_deal_id;
    const contactId = syncResult?.contact_id || memo?.hubspotContactId || memo?.hubspot_contact_id;
    if (!dealId && !contactId) return;
    let cancelled = false;
    api
      .get<{ metadata?: { company_domain?: string; api_domain?: string } }>("/crm/pipedrive/connection")
      .then((conn) => {
        if (cancelled) return;
        const domain = pipedriveCompanyDomain(conn?.metadata);
        setCrmViewUrl(
          pipedriveRecordUrl(domain, "deal", dealId) || pipedriveRecordUrl(domain, "person", contactId),
        );
      })
      .catch(() => {
        if (!cancelled) setCrmViewUrl(null);
      });
    return () => {
      cancelled = true;
    };
  }, [
    syncResult,
    memo?.hubspotDealId,
    memo?.hubspot_deal_id,
    memo?.hubspotContactId,
    memo?.hubspot_contact_id,
  ]);

  const handleReExtract = async () => {
    if (!id) return;
    setIsReExtracting(true);
    try {
      clearCachedPreview(id);
      const updated = await memosApi.reExtract(id);
      setMemo(updated);
      toast.success("Re-extraction started. AI is extracting CRM fields...");
    } catch (err: any) {
      toast.error(err?.data?.detail || "Re-extract failed");
    } finally {
      setIsReExtracting(false);
    }
  };

  const handleReTranscribe = async () => {
    if (!id) return;
    setIsReTranscribing(true);
    try {
      clearCachedPreview(id);
      const updated = await memosApi.reTranscribe(id);
      setMemo(updated);
      toast.success("Re-transcribing from the HubSpot recording…");
    } catch (err: any) {
      toast.error(err?.data?.detail || "Re-transcribe failed");
    } finally {
      setIsReTranscribing(false);
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

  useEffect(() => {
    if (!id || !memo || memo.status !== "pending_transcript" || isConfirmingTranscript) return;
    if (memo.userId && user?.id && memo.userId !== user.id) return;
    if (!memo.transcript?.trim()) return;
    void handleConfirmTranscript();
  }, [id, memo?.status, memo?.transcript, isConfirmingTranscript]);

  if (isLoading && !memo) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh]">
        <VocifyLoader size="lg" label="Loading conversation..." />
      </div>
    );
  }

  if (error || !memo) {
    return (
      <div className="max-w-2xl mx-auto text-center space-y-6 pt-20">
        <div className="w-20 h-20 bg-destructive/10 rounded-full flex items-center justify-center mx-auto">
          <AlertCircle className="h-10 w-10 text-destructive" />
        </div>
        <h2 className="text-2xl font-normal tracking-tight">Something went wrong</h2>
        <p className="text-muted-foreground">{error || "Conversation not found."}</p>
        <Button asChild variant="outline" className="rounded-full">
          <Link to="/dashboard/memos">Back to Memos</Link>
        </Button>
      </div>
    );
  }

  const isOwnMemo = !memo.userId || memo.userId === user?.id;
  const canViewCompany = canViewCompanyActivity(user?.company?.role);
  const authorName = authorChipLabel(memo.authorName, memo.userId, user?.id);
  const isProcessing = ["uploading", "transcribing", "extracting", "pending_transcript"].includes(memo.status);
  const extractionFailed = memo.status === "failed";
  const hasExtraction = !isProcessing && !extractionFailed && !!memo.extraction;
  const canSeeReview = hasExtraction && (isOwnMemo || canViewCompany);
  const extraction = memo.extraction || {};
  const isCallMemo =
    memo.source === "hubspot_call" ||
    memo.source === "vocify_call" ||
    Boolean(memo.hubspotEngagementId);
  const canReTranscribe =
    isOwnMemo &&
    isCallMemo &&
    Boolean(memo.audioUrl) &&
    memo.status !== "approved" &&
    !isProcessing;
  const previewRefreshKey = `${memo.status}:${memo.processedAt || ""}:${memo.transcript?.length || 0}`;

  const loggedAs = user?.fullName || user?.email || "you";
  const attachedContact = reviewContactName || extraction.contactName || extraction.contact_name;
  const attachedDeal = syncResult?.deal_name || extraction.companyName || extraction.company_name;

  if (syncResult) {
    const viewUrl = syncResult.deal_url || syncResult.contact_url || crmViewUrl;
    const { crmName, viewInCrm } = labelsFromDealUrl(viewUrl);
    return (
      <div className={`max-w-2xl mx-auto ${THEME_TOKENS.motion.fadeIn} text-center`}>
        <Link
          to="/dashboard/memos"
          aria-label="Back to memos"
          className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground/60 hover:text-beige hover:bg-beige/10 mb-12 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.container} p-16 relative overflow-hidden group`}>
          <div className="absolute inset-0 bg-gradient-to-br from-success/10 to-transparent" />
          <div className="relative z-10">
            <div className={`w-20 h-20 mx-auto mb-8 ${THEME_TOKENS.radius.card} bg-success/10 flex items-center justify-center`}>
              <Check className="h-10 w-10 text-success shadow-[0_0_15px_rgba(34,197,94,0.3)]" />
            </div>
            <h2 className="text-3xl font-normal tracking-tight text-foreground mb-4">Sync Successful</h2>
            <p className="text-muted-foreground mb-10 leading-relaxed mx-auto max-w-sm">
              Synced{" "}
              {attachedContact ? (
                <span className="text-foreground">{attachedContact}</span>
              ) : (
                "this call"
              )}
              {attachedDeal ? (
                <>
                  {" "}on{" "}
                  <span className="text-foreground">{attachedDeal}</span>
                </>
              ) : null}{" "}
              to {crmName}.
              {crmName === "HubSpot" ? ` Logged as ${loggedAs}.` : ""}
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              {viewUrl ? (
                <Button variant="hero" size="xl" asChild className="rounded-full bg-beige text-cream px-10 shadow-large hover:opacity-90 transition-opacity">
                  <a href={viewUrl} target="_blank" rel="noopener noreferrer">
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
          aria-label="Back to memos"
          className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground/60 hover:text-beige hover:bg-beige/10 mb-10 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>

      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          {memoListTitle(memo)}
          {memoListSubtitle(memo) ? (
            <span className={THEME_TOKENS.typography.accentTitle}> {memoListSubtitle(memo)}</span>
          ) : (
            <span className={THEME_TOKENS.typography.accentTitle}> Details</span>
          )}
        </h1>
        {!isOwnMemo && authorName ? (
          <div className="flex flex-wrap items-center gap-2">
            <AuthorLabel name={authorName} />
          </div>
        ) : null}
        <p className={THEME_TOKENS.typography.body}>
          {isProcessing
            ? "AI is extracting CRM fields..."
            : extractionFailed
              ? "Extraction failed. Re-extract to continue."
              : !isOwnMemo
                ? `Recorded by ${memo.authorName || "a teammate"}. Review and sync to CRM.`
              : memo.status === "approved"
                ? attachedContact
                  ? `Already written to CRM for ${attachedContact}${attachedDeal ? ` · ${attachedDeal}` : ""}. Open later to check or correct.`
                  : "Already written to CRM. Open later to check or correct."
              : attachedContact
                ? `Attached to ${attachedContact}${attachedDeal ? ` · ${attachedDeal}` : ""}. Review and sync to CRM.`
                : "Review and sync to CRM."}
        </p>
      </div>

      {extractionFailed && isOwnMemo && (
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
              <VocifySpinner size={16} className="mr-2" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            {isReExtracting ? "Re-extracting..." : "Re-extract"}
          </Button>
        </div>
      )}

      <div className={`grid gap-8 ${canSeeReview ? "lg:grid-cols-5 items-start" : ""}`}>
        {/* Left: Transcript (full width when pending/extracting, col-span-2 when has extraction) */}
        <div
          className={
            canSeeReview
              ? "lg:col-span-2 sticky top-20 max-h-[calc(100vh-6rem)] flex flex-col gap-4 self-start overflow-y-auto pr-1 scrollbar-thin"
              : "space-y-6"
          }
        >
          {memo.audioUrl && (
            <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.card} p-5 shrink-0`}>
              <div className="flex items-center gap-4">
                <Button
                  variant="outline"
                  size="icon"
                  onClick={togglePlay}
                  className="rounded-full w-10 h-10 bg-beige text-cream border-none hover:opacity-90 transition-opacity shrink-0"
                >
                  {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 ml-0.5" />}
                </Button>
                <div className="flex-1 space-y-1.5 min-w-0">
                  <div className="h-1.5 bg-foreground/5 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-beige rounded-full shadow-[0_0_10px_rgba(245,215,176,0.3)] transition-all duration-100"
                      style={{ width: `${(currentTime / (duration || 1)) * 100}%` }}
                    />
                  </div>
                  <div className="flex justify-between items-center text-[10px]">
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

          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 sm:p-8 flex flex-col ${canSeeReview ? "flex-1 min-h-0" : ""}`}>
            <div className="flex items-center justify-between gap-3 mb-6 shrink-0">
              <h3 className={THEME_TOKENS.typography.capsLabel}>Transcript</h3>
              <div className="flex items-center gap-2">
                {canReTranscribe ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={handleReTranscribe}
                    disabled={isReTranscribing}
                    aria-label="Re-transcribe from recording"
                    title="Re-transcribe from recording"
                    className="rounded-full border-beige/40 hover:bg-beige/10 h-8 w-8 shrink-0"
                  >
                    {isReTranscribing ? (
                      <VocifySpinner size={14} />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5" />
                    )}
                  </Button>
                ) : null}
                {memo.transcriptConfidence ? (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[9px] font-medium bg-success/10 text-success">
                    <span className="w-1.5 h-1.5 rounded-full bg-success shadow-[0_0_8px_rgba(34,197,94,0.4)]" />
                    {Math.round(memo.transcriptConfidence * 100)}% accuracy
                  </span>
                ) : null}
              </div>
            </div>
            {memo.transcript ? (
              <TranscriptConversation
                transcript={memo.transcript}
                contactName={reviewContactName || extraction.contactName}
                className={
                  canSeeReview
                    ? (memo.audioUrl
                        ? "max-h-[calc(100vh-22rem)] overflow-y-auto pr-2 scrollbar-thin"
                        : "max-h-[calc(100vh-16rem)] overflow-y-auto pr-2 scrollbar-thin")
                    : "max-h-[500px] overflow-y-auto pr-2 scrollbar-thin"
                }
              />
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <VocifyLoader size="md" label={isProcessing ? "Extracting CRM fields..." : "No transcript yet"} />
              </div>
            )}
          </div>
        </div>

        {/* Right: HubSpotSyncPreview (only when extraction ready) */}
        {canSeeReview && (
          <div className="lg:col-span-3 min-w-0">
            {memo.status === "approved" && crmViewUrl ? (
              <div className="mb-4 flex justify-end">
                <Button variant="outline" asChild className="rounded-full">
                  <a href={crmViewUrl} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-4 w-4 mr-2" />
                    {labelsFromDealUrl(crmViewUrl).viewInCrm}
                  </a>
                </Button>
              </div>
            ) : null}
            {isOwnMemo && id ? (
              <InteractionObjections
                memoId={id}
                coverage="unavailable"
                patterns={[]}
                notes={[]}
                canPlaySpan={false}
                offsetMs={Math.round(currentTime * 1000)}
              />
            ) : null}
            {isOwnMemo && id ? (
              <MeetingProposalReview
                proposal={null}
                extractionPending={memo.status === "extracting" || memo.status === "transcribing"}
              />
            ) : null}
            {isOwnMemo && id ? <CoachingScore memoId={id} /> : null}
            {isOwnMemo && id ? <FollowupCard memoId={id} /> : null}
            <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 sm:p-8 md:p-10`}>
              <HubSpotSyncPreview
                key={id || ""}
                memoId={id || ""}
                initialDealId={dealIdFromUrl}
                initialContactId={memo?.hubspotContactId || memo?.hubspot_contact_id}
                fallbackContactName={extraction.contactName || extraction.contact_name}
                previewRefreshKey={previewRefreshKey}
                callSummary={extraction.summary}
                alreadyWritten={memo.status === "approved"}
                onSuccess={handleSyncSuccess}
                onContactName={setReviewContactName}
              />
            </div>
          </div>
        )}

        {isProcessing && memo?.transcript && !hasExtraction && (
          <div className="col-span-full flex flex-col items-center justify-center py-16 border border-dashed border-border/40 rounded-[2rem] bg-secondary/[0.02]">
            <VocifyLoader size="lg" label="AI is analyzing your sales conversation" />
            <p className="text-[10px] font-medium text-muted-foreground/40 mt-2">
              Extracting CRM fields...
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default MemoDetail;
