import { useState, useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Play, Pause, Check, Edit, X, ChevronDown, ExternalLink, Sparkles, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { HubSpotSyncPreview } from "@/components/dashboard/hubspot/HubSpotSyncPreview";
import { api } from "@/shared/lib/api-client";
import { useAuth } from "@/features/auth";

const MemoDetail = () => {
  const { id } = useParams();
  const { user } = useAuth();
  const [memo, setMemo] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audio] = useState(new Audio());
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [syncResult, setSyncResult] = useState<any>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

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
    if (memo && ['uploading', 'transcribing', 'extracting'].includes(memo.status)) {
      interval = window.setInterval(fetchMemo, 3000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [id, memo?.status]);

  const handleSyncSuccess = (result: any) => {
    setSyncResult(result);
    setIsPreviewOpen(false);
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

  const extraction = memo.extraction || {};
  const isProcessing = ['uploading', 'transcribing', 'extracting'].includes(memo.status);

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
              <Button variant="hero" size="xl" asChild className="rounded-full bg-beige text-cream px-10 shadow-large hover:scale-105 transition-transform">
                <a href={syncResult.deal_url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="h-4 w-4 mr-2" />
                  View in HubSpot
                </a>
              </Button>
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
          {isProcessing ? "AI is currently analyzing your conversation..." : "Review and approve your CRM sync."}
        </p>
      </div>

      <div className="grid lg:grid-cols-5 gap-8">
        {/* Left Column - Transcript */}
        <div className="lg:col-span-2 space-y-6">
          {/* Audio Player */}
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
            <div className="prose prose-sm text-muted-foreground max-h-[500px] overflow-y-auto pr-4 scrollbar-thin">
              {memo.transcript ? (
                memo.transcript.split('\n').map((line: string, i: number) => (
                  <p key={i} className="mb-4 leading-relaxed tracking-tight">{line}</p>
                ))
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-center opacity-40">
                  <Sparkles className="h-8 w-8 mb-4 animate-pulse" />
                  <p className="text-[10px] font-black uppercase tracking-widest">Generating transcript...</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column - Extracted Data */}
        <div className="lg:col-span-3">
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-10`}>
            <h3 className={`${THEME_TOKENS.typography.capsLabel} mb-10`}>Extracted CRM Data</h3>
            
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
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Company</label>
                      <Input defaultValue={extraction.companyName} className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold" />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Deal Amount</label>
                      <Input defaultValue={extraction.dealAmount} className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold" />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Deal Stage</label>
                      <div className="relative">
                        <select className="w-full h-12 px-6 rounded-full border border-border/40 bg-secondary/5 text-foreground appearance-none cursor-pointer font-bold focus:outline-none">
                          <option selected={extraction.dealStage === 'Discovery'}>Discovery</option>
                          <option selected={extraction.dealStage === 'Proposal'}>Proposal</option>
                          <option selected={extraction.dealStage === 'Negotiation'}>Negotiation</option>
                          <option selected={extraction.dealStage === 'Closed Won'}>Closed Won</option>
                        </select>
                        <ChevronDown className="absolute right-6 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40 pointer-events-none" />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Close Date</label>
                      <Input type="date" defaultValue={extraction.closeDate} className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold" />
                    </div>
                  </div>
                </div>

                {/* Contact */}
                <div>
                  <h4 className="text-[10px] font-black uppercase tracking-widest text-beige mb-6 pb-2 border-b border-beige/10">
                    Contact Person
                  </h4>
                  <div className="grid sm:grid-cols-3 gap-6">
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Name</label>
                      <Input defaultValue={extraction.contactName} className="bg-secondary/5 border-border/40 rounded-full px-4 h-11 font-bold" />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Role</label>
                      <Input defaultValue={extraction.contactRole} className="bg-secondary/5 border-border/40 rounded-full px-4 h-11 font-bold text-xs" />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Email</label>
                      <Input defaultValue={extraction.contactEmail} className="bg-secondary/5 border-border/40 rounded-full px-4 h-11 font-bold text-xs" />
                    </div>
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
                        defaultValue={extraction.painPoints?.map((p: string) => `• ${p}`).join('\n')} 
                        rows={3}
                        className="bg-secondary/5 border-border/40 rounded-[1.5rem] px-6 py-4 font-medium leading-relaxed"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className={`${THEME_TOKENS.typography.capsLabel} ml-1`}>Next Steps</label>
                      <Textarea 
                        defaultValue={extraction.nextSteps?.map((s: string) => `• ${s}`).join('\n')} 
                        rows={3}
                        className="bg-secondary/5 border-border/40 rounded-[1.5rem] px-6 py-4 font-medium leading-relaxed"
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex items-center justify-between gap-4 mt-12 pt-10 border-t border-border/40">
              <button className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/30 hover:text-destructive transition-colors px-6">
                Reject Memo
              </button>
              <div className="flex items-center gap-4">
                <Button 
                  variant="hero" 
                  disabled={isProcessing}
                  onClick={() => setIsPreviewOpen(true)} 
                  className="rounded-full px-8 h-12 text-[10px] font-black uppercase tracking-widest bg-beige text-cream shadow-large hover:scale-105 transition-transform"
                >
                  <Sparkles className="h-4 w-4 mr-2" />
                  Update CRM Fields
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={isPreviewOpen} onOpenChange={setIsPreviewOpen}>
        <DialogContent className={`${THEME_TOKENS.radius.container} border-none p-10 bg-white shadow-large max-w-2xl max-h-[90vh] overflow-y-auto`}>
          <DialogHeader className="mb-8">
            <DialogTitle className="text-2xl font-black tracking-tight flex items-center gap-3">
              Review <span className="text-beige">CRM Updates</span>
            </DialogTitle>
          </DialogHeader>
          
          <HubSpotSyncPreview 
            memoId={id || ""} 
            onSuccess={handleSyncSuccess} 
          />
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MemoDetail;
