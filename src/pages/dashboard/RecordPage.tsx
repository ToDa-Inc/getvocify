import { useEffect, useState, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Mic, Square, Upload, ArrowLeft, Sparkles, Building2, User, DollarSign, Calendar, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { 
  useMediaRecorder, 
  useAudioUpload, 
  useRealtimeTranscription 
} from "@/features/recording";
import {
  AudioWaveform,
  AudioPreview,
  UploadProgress,
  RecordingError,
  LiveTranscript,
} from "@/features/recording/components";
import { AUDIO, ROUTES } from "@/shared/lib/constants";
import { isSupportedAudioType, formatFileSize } from "@/features/recording/types";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

const RecordPage = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [uploadedMemoId, setUploadedMemoId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    state,
    duration,
    error,
    audio,
    visualization,
    start,
    stop,
    cancel,
    reset,
  } = useMediaRecorder();

  const {
    upload,
    progress,
    isUploading,
    error: uploadError,
    reset: resetUpload,
  } = useAudioUpload();

  const {
    isTranscribing,
    isConnected,
    error: transcriptionError,
    finalTranscript,
    interimTranscript,
    fullTranscript,
    providerTranscripts,
    start: startTranscription,
    stop: stopTranscription,
    reset: resetTranscription,
  } = useRealtimeTranscription(
    user?.id || 'anonymous',
    'multi'
  );

  useEffect(() => {
    if (progress?.complete && uploadedMemoId) {
      setTimeout(() => {
        navigate(ROUTES.MEMO_DETAIL(uploadedMemoId));
        toast.success("Voice memo uploaded! Processing will take about 30 seconds.");
      }, 1000);
    }
  }, [progress?.complete, uploadedMemoId, navigate]);

  const handleRecordClick = async () => {
    if (state === "idle") {
      // Start recording and get the shared stream
      const stream = await start();
      
      // Start real-time transcription using the same stream
      if (stream) {
        await startTranscription(stream);
      }
    } else if (state === "recording") {
      // Stop both recording and transcription
      stop();
      stopTranscription();
    }
  };

  const handleUpload = async () => {
    if (!audio) return;
    try {
      const transcript = fullTranscript || undefined;
      const memoId = await upload(audio, transcript);
      setUploadedMemoId(memoId);
      resetTranscription();
    } catch (err) {
      toast.error(uploadError || "Failed to upload audio");
    }
  };

  const handleFileSelect = async (file: File) => {
    if (!isSupportedAudioType(file)) {
      toast.error("Unsupported file type. Please use MP3, WAV, or M4A.");
      return;
    }
    if (file.size > AUDIO.MAX_FILE_SIZE_BYTES) {
      toast.error(`File too large. Maximum size is ${formatFileSize(AUDIO.MAX_FILE_SIZE_BYTES)}`);
      return;
    }
    const audioUrl = URL.createObjectURL(file);
    const audioBlob = file;
    const estimatedDuration = (file.size / (1024 * 1024)) * 60;
    try {
      const memoId = await upload({
        blob: audioBlob,
        url: audioUrl,
        duration: estimatedDuration,
        mimeType: file.type,
        size: file.size,
      });
      setUploadedMemoId(memoId);
    } catch (err) {
      URL.revokeObjectURL(audioUrl);
      toast.error(uploadError || "Failed to upload audio");
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDropzoneClick = () => fileInputRef.current?.click();
  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  };
  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => e.preventDefault();
  const handleReRecord = () => {
    cancel();
    resetUpload();
    resetTranscription();
  };
  const handleErrorRetry = () => {
    reset();
    resetUpload();
    start();
  };
  const handleErrorReset = () => {
    reset();
    resetUpload();
    resetTranscription();
  };

  const getStatusText = () => {
    switch (state) {
      case "idle": return "Ready to record";
      case "requesting": return "Requesting microphone access...";
      case "recording": return "Recording...";
      case "stopped": return "Recording complete";
      case "uploading": return "Uploading...";
      case "error": return "Error occurred";
      default: return "";
    }
  };

  if (state === "error" && error) {
    return (
      <div className={`max-w-2xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
        <Link to={ROUTES.DASHBOARD} className={`inline-flex items-center gap-2 ${THEME_TOKENS.typography.capsLabel} text-muted-foreground/60 hover:text-beige mb-8 transition-colors group`}>
          <ArrowLeft className="h-3 w-3 group-hover:-translate-x-1 transition-transform" />
          Back to Dashboard
        </Link>
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-12`}>
          <RecordingError error={error} onRetry={handleErrorRetry} onReset={handleErrorReset} />
        </div>
      </div>
    );
  }

  if (isUploading && progress) {
    return (
      <div className={`max-w-2xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
        <Link to={ROUTES.DASHBOARD} className={`inline-flex items-center gap-2 ${THEME_TOKENS.typography.capsLabel} text-muted-foreground/60 hover:text-beige mb-8 transition-colors group`}>
          <ArrowLeft className="h-3 w-3 group-hover:-translate-x-1 transition-transform" />
          Back to Dashboard
        </Link>
        <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-12 text-center`}>
          <p className={`${THEME_TOKENS.typography.capsLabel} mb-10`}>{getStatusText()}</p>
          <div className={`relative w-48 h-48 mx-auto mb-8 ${THEME_TOKENS.radius.pill} bg-secondary/5 flex items-center justify-center`}>
            <div className="flex flex-col items-center gap-4">
              <div className="w-6 h-6 border-2 border-beige border-t-transparent rounded-full animate-spin" />
              <div className="text-4xl font-black text-foreground">{formatTime(duration)}</div>
            </div>
          </div>
          <UploadProgress progress={progress} className="mb-4" />
          <p className="text-sm text-muted-foreground">This usually takes 30 seconds</p>
        </div>
      </div>
    );
  }

  if (state === "stopped" && audio) {
    return (
      <div className={`max-w-6xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
        <Link 
          to={ROUTES.DASHBOARD} 
          className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 hover:text-beige mb-10 transition-colors group"
        >
          <ArrowLeft className="h-3 w-3 group-hover:-translate-x-1 transition-transform" />
          Back to Dashboard
        </Link>

        <div className={V_PATTERNS.dashboardHeader}>
          <h1 className={THEME_TOKENS.typography.pageTitle}>
            Review <span className={THEME_TOKENS.typography.accentTitle}>Recording</span>
          </h1>
          <p className={THEME_TOKENS.typography.body}>Preview your transcript and extracted CRM fields.</p>
        </div>

        <div className="grid lg:grid-cols-5 gap-8">
          {/* Left Column - Playback & Transcripts */}
          <div className="lg:col-span-2 space-y-6">
            {/* Audio Player Card */}
            <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.card} p-6`}>
              <AudioPreview audio={audio} onReRecord={handleReRecord} onUpload={handleUpload} />
            </div>

            {/* Transcription Comparison/Preview */}
            <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
              <div className="flex items-center justify-between mb-8">
                <h3 className={THEME_TOKENS.typography.capsLabel}>Captured Transcripts</h3>
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest bg-success/10 text-success">
                  <span className="w-1.5 h-1.5 rounded-full bg-success shadow-[0_0_8px_rgba(34,197,94,0.4)]" />
                  Real-time processed
                </span>
              </div>
              
              <div className="space-y-6">
                {Object.entries(providerTranscripts).map(([provider, data]) => (
                  <div key={provider} className="space-y-2">
                    <div className="flex items-center gap-2 px-1">
                      <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground/40">{provider}</span>
                    </div>
                    <div className="rounded-2xl bg-secondary/[0.03] p-5 border border-border/20 max-h-[250px] overflow-y-auto scrollbar-thin">
                      <p className="text-sm leading-relaxed text-muted-foreground/80 font-medium tracking-tight">
                        {data.full || "No transcript captured for this provider."}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column - Extraction Schema Preview */}
          <div className="lg:col-span-3">
            <div className={cn(
              THEME_TOKENS.cards.base,
              THEME_TOKENS.radius.card,
              "p-10 relative overflow-hidden"
            )}>
              <div className="absolute top-0 right-0 p-8">
                <Sparkles className="h-5 w-5 text-beige animate-pulse opacity-20" />
              </div>

              <div className="relative z-10">
                <h3 className={`${THEME_TOKENS.typography.capsLabel} mb-10`}>CRM Field Preview</h3>
                
                <div className="space-y-10">
                  {/* Deal Details */}
                  <div>
                    <h4 className="text-[10px] font-black uppercase tracking-widest text-beige mb-6 pb-2 border-b border-beige/10 flex items-center gap-2">
                      <Building2 className="h-3.5 w-3.5" />
                      Deal Details
                    </h4>
                    <div className="grid sm:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <label className={`${THEME_TOKENS.typography.capsLabel} ml-1 !text-foreground/30`}>Company</label>
                        <div className="h-12 w-full rounded-full border border-dashed border-border/40 bg-secondary/[0.02] flex items-center px-6 text-xs text-muted-foreground/40 font-medium italic">
                          Waiting for extraction...
                        </div>
                      </div>
                      <div className="space-y-2">
                        <label className={`${THEME_TOKENS.typography.capsLabel} ml-1 !text-foreground/30`}>Deal Amount</label>
                        <div className="h-12 w-full rounded-full border border-dashed border-border/40 bg-secondary/[0.02] flex items-center px-6 text-xs text-muted-foreground/40 font-medium italic">
                          Waiting for extraction...
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Contact Person */}
                  <div>
                    <h4 className="text-[10px] font-black uppercase tracking-widest text-beige mb-6 pb-2 border-b border-beige/10 flex items-center gap-2">
                      <User className="h-3.5 w-3.5" />
                      Contact Person
                    </h4>
                    <div className="grid sm:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <label className={`${THEME_TOKENS.typography.capsLabel} ml-1 !text-foreground/30`}>Full Name</label>
                        <div className="h-12 w-full rounded-full border border-dashed border-border/40 bg-secondary/[0.02] flex items-center px-6 text-xs text-muted-foreground/40 font-medium italic">
                          Waiting for extraction...
                        </div>
                      </div>
                      <div className="space-y-2">
                        <label className={`${THEME_TOKENS.typography.capsLabel} ml-1 !text-foreground/30`}>Email Address</label>
                        <div className="h-12 w-full rounded-full border border-dashed border-border/40 bg-secondary/[0.02] flex items-center px-6 text-xs text-muted-foreground/40 font-medium italic">
                          Waiting for extraction...
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Placeholder for more schemas */}
                  <div className="pt-10 border-t border-border/40">
                    <div className="flex flex-col items-center justify-center py-12 px-6 rounded-[2rem] border border-dashed border-border/30 bg-muted/5">
                      <Sparkles className="h-8 w-8 text-beige/20 mb-4" />
                      <p className="text-sm font-bold text-foreground/40 mb-1">AI Extraction Ready</p>
                      <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/20 text-center max-w-[200px]">
                        Our model will analyze your conversation and populate these fields automatically.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Final Action */}
                <div className="mt-12 pt-10 border-t border-border/40 flex justify-end">
                  <Button 
                    variant="hero" 
                    size="xl"
                    onClick={handleUpload}
                    className="rounded-full px-12 h-16 text-[10px] font-black uppercase tracking-widest bg-beige text-cream shadow-large hover:scale-105 active:scale-95 transition-all"
                  >
                    Confirm & Start AI Extraction
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`max-w-3xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
      <Link to={ROUTES.DASHBOARD} className={`inline-flex items-center gap-2 ${THEME_TOKENS.typography.capsLabel} text-muted-foreground/60 hover:text-beige mb-10 transition-colors group`}>
        <ArrowLeft className="h-3 w-3 group-hover:-translate-x-1 transition-transform" />
        Back to Dashboard
      </Link>

      <div className={V_PATTERNS.dashboardHeader + " text-center"}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          New <span className={THEME_TOKENS.typography.accentTitle}>Recording</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>Capture your thoughts while they're fresh.</p>
      </div>

      <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-12 text-center relative overflow-hidden group`}>
        <div className="absolute inset-0 bg-gradient-to-br from-beige/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
        <p className={`${THEME_TOKENS.typography.capsLabel} mb-10 transition-colors relative z-10 ${state === "recording" ? "text-destructive" : "text-muted-foreground/40"}`}>{getStatusText()}</p>
        <div className={`relative w-56 h-56 mx-auto mb-12 ${THEME_TOKENS.radius.pill} bg-secondary/5 flex items-center justify-center border border-border/20 z-10`}>
          {state === "recording" && (
            <>
              <div className="absolute inset-0 rounded-full border-4 border-destructive/20 animate-ping" />
              <div className="absolute inset-0 rounded-full border-2 border-destructive/40" />
            </>
          )}
          <div className="flex flex-col items-center gap-6">
            <AudioWaveform visualization={visualization} isRecording={state === "recording"} />
            <div className={`text-5xl font-black tracking-tighter transition-colors ${state === "recording" ? "text-destructive" : "text-foreground"}`}>{formatTime(duration)}</div>
          </div>
        </div>

        {state === "recording" && (
          <div className="mb-12 w-full animate-in zoom-in-95 duration-500 relative z-10">
            <LiveTranscript 
              finalTranscript={finalTranscript} 
              interimTranscript={interimTranscript} 
              providerTranscripts={providerTranscripts}
              isActive={isTranscribing && isConnected} 
            />
          </div>
        )}

        <div className="relative z-10">
          <Button
            variant={state === "recording" ? "destructive" : "default"}
            size="xl"
            onClick={handleRecordClick}
            disabled={state === "requesting"}
            className={`rounded-full mx-auto px-10 h-16 shadow-large transition-all duration-500 hover:scale-105 active:scale-95 ${state !== "recording" ? "bg-beige text-cream" : "bg-destructive text-white"}`}
          >
            {state === "requesting" ? (
              <div className="w-6 h-6 border-2 border-cream border-t-transparent rounded-full animate-spin" />
            ) : state === "recording" ? (
              <>
                <Square className="h-5 w-5 mr-3 fill-current" />
                <span className="text-[10px] font-black uppercase tracking-widest">Stop Recording</span>
              </>
            ) : (
              <>
                <Mic className="h-6 w-6 mr-3" />
                <span className="text-[10px] font-black uppercase tracking-widest">Start Recording</span>
              </>
            )}
          </Button>
          <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/30 mt-6">
            {state === "idle" && "Tap to start or upload below"}
            {state === "recording" && "Tap stop when finished"}
            {state === "requesting" && "Checking microphone permissions..."}
          </p>
        </div>

        {state === "idle" && (
          <div className="mt-16 pt-12 border-t border-border/40 relative z-10">
            <p className={`${THEME_TOKENS.typography.capsLabel} mb-8`}>OR IMPORT AUDIO FILE</p>
            <input ref={fileInputRef} type="file" accept="audio/*" onChange={handleFileInputChange} className="hidden" />
            <div
              onClick={handleDropzoneClick}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.card} p-10 hover:border-beige/20 transition-all cursor-pointer group/upload shadow-[inset_4px_4px_8px_rgba(255,255,255,0.8),inset_-4px_-4px_8px_rgba(0,0,0,0.02)]`}
            >
              <div className="w-16 h-16 bg-beige/10 rounded-2xl flex items-center justify-center mx-auto mb-6 group-hover/upload:scale-110 transition-transform">
                <Upload className="h-8 w-8 text-beige" />
              </div>
              <p className="text-sm font-bold text-foreground mb-2 leading-tight">Drop your recording here</p>
              <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/40">MP3, WAV, M4A up to {formatFileSize(AUDIO.MAX_FILE_SIZE_BYTES)}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default RecordPage;
