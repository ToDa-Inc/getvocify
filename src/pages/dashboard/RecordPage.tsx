import { useEffect, useState, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Mic, Square, Upload, ArrowLeft, FileText } from "lucide-react";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { memoKeys } from "@/features/memos/api";
import { AUDIO, ROUTES } from "@/shared/lib/constants";
import { isSupportedAudioType, formatFileSize } from "@/features/recording/types";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

const RecordPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [uploadedMemoId, setUploadedMemoId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importPhase, setImportPhase] = useState<"idle" | "uploading" | "done">("idle");

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
    uploadTranscriptOnly,
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
        toast.success("Memo created! AI is extracting CRM fields...");
      }, 800);
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
    try {
      if (fullTranscript?.trim()) {
        // Transcript-only: real-time transcription produced the text, no audio sent
        const memoId = await uploadTranscriptOnly(fullTranscript);
        setUploadedMemoId(memoId);
        resetTranscription();
      } else if (audio) {
        // Fallback: no real-time transcript, send audio for server-side transcription
        const memoId = await upload(audio);
        setUploadedMemoId(memoId);
      } else {
        toast.error("No transcript available. Please try recording again.");
      }
    } catch (err) {
      toast.error(uploadError || "Failed to upload");
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

  // All useState hooks must be declared before any conditional returns
  const [editedTranscript, setEditedTranscript] = useState("");
  const [importTranscript, setImportTranscript] = useState("");
  const [activeTab, setActiveTab] = useState("record");

  useEffect(() => {
    if (fullTranscript) setEditedTranscript(fullTranscript);
  }, [fullTranscript]);

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

  if (importPhase === "uploading" || importPhase === "done") {
    return (
      <div className={`max-w-2xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
        <div className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground/50 mb-10">
          <ArrowLeft className="h-3 w-3" />
          Back to Dashboard
        </div>
        <div
          className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-12 text-center transition-all duration-500 ${
            importPhase === "done" ? "ring-2 ring-success/30 bg-success/5" : ""
          }`}
        >
          <div className="relative w-32 h-32 mx-auto mb-8 flex items-center justify-center">
            {importPhase === "uploading" ? (
              <>
                <div className="absolute inset-0 rounded-full border-2 border-beige/20" />
                <div className="absolute inset-0 rounded-full border-2 border-beige border-t-transparent animate-spin" />
                <FileText className="h-12 w-12 text-beige/80 relative z-10" />
              </>
            ) : (
              <div className="w-20 h-20 rounded-full bg-success/10 flex items-center justify-center animate-in zoom-in-95 duration-300">
                <svg className="w-10 h-10 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
            )}
          </div>
          <h2 className="text-xl font-black text-foreground mb-2">
            {importPhase === "uploading" ? "Importing transcript..." : "Done!"}
          </h2>
          <p className="text-sm text-muted-foreground">
            {importPhase === "uploading"
              ? "Creating your memo and preparing the review step..."
              : "Taking you to review your transcript..."}
          </p>
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
          <p className={`${THEME_TOKENS.typography.capsLabel} mb-10`}>
            {isUploading ? "Processing your memo..." : getStatusText()}
          </p>
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

  const hasTranscript = !!fullTranscript?.trim();
  const showReview = state === "stopped" && (hasTranscript || audio);

  if (showReview) {
    return (
      <div className={`max-w-2xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
        <Link 
          to={ROUTES.DASHBOARD} 
          className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 hover:text-beige mb-10 transition-colors group"
        >
          <ArrowLeft className="h-3 w-3 group-hover:-translate-x-1 transition-transform" />
          Back to Dashboard
        </Link>

        <div className={V_PATTERNS.dashboardHeader}>
          <h1 className={THEME_TOKENS.typography.pageTitle}>
            Review <span className={THEME_TOKENS.typography.accentTitle}>Transcript</span>
          </h1>
          <p className={THEME_TOKENS.typography.body}>
            {hasTranscript
              ? "Review and edit your transcript below. When ready, accept to extract CRM fields and sync."
              : "Waiting for transcript... If it doesn't appear, you can upload the recording for server-side transcription."}
          </p>
        </div>

        {hasTranscript ? (
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
            <div className="flex items-center justify-between mb-6">
              <h3 className={THEME_TOKENS.typography.capsLabel}>Your Transcript</h3>
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest bg-success/10 text-success">
                <span className="w-1.5 h-1.5 rounded-full bg-success shadow-[0_0_8px_rgba(34,197,94,0.4)]" />
                Real-time
              </span>
            </div>
            <textarea
              value={editedTranscript}
              onChange={(e) => setEditedTranscript(e.target.value)}
              placeholder="Edit your transcript..."
              className="w-full min-h-[320px] rounded-2xl bg-secondary/[0.03] p-6 border border-border/20 text-sm leading-relaxed text-muted-foreground/90 font-medium tracking-tight whitespace-pre-wrap resize-y focus:outline-none focus:ring-2 focus:ring-beige/30 focus:border-beige/40 placeholder:text-muted-foreground/40"
            />
            <div className="flex gap-3 mt-6">
              <Button variant="outline" onClick={handleReRecord} disabled={isUploading} className="flex-1 rounded-full">
                Re-record
              </Button>
              <Button
                variant="hero"
                disabled={isUploading}
                onClick={async () => {
                  if (!editedTranscript.trim()) {
                    toast.error("Transcript cannot be empty");
                    return;
                  }
                  try {
                    const memoId = await uploadTranscriptOnly(editedTranscript.trim());
                    resetTranscription();
                    toast.success("Memo created! AI is extracting CRM fields...");
                    window.location.href = ROUTES.MEMO_DETAIL(memoId);
                  } catch {
                    toast.error(uploadError || "Failed to upload");
                  }
                }}
                className="flex-1 rounded-full bg-beige text-cream"
              >
                {isUploading ? (
                  <>
                    <span className="w-4 h-4 border-2 border-cream border-t-transparent rounded-full animate-spin mr-2" />
                    Processing...
                  </>
                ) : (
                  "Accept & Continue"
                )}
              </Button>
            </div>
          </div>
        ) : audio ? (
          <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.card} p-6`}>
            <AudioPreview audio={audio} onReRecord={handleReRecord} onUpload={handleUpload} />
          </div>
        ) : null}
      </div>
    );
  }

  const handleImportSubmit = async () => {
    const trimmed = importTranscript.trim();
    if (!trimmed) {
      toast.error("Please paste a transcript");
      return;
    }
    setImportPhase("uploading");
    try {
      const memoId = await uploadTranscriptOnly(trimmed, {
        sourceType: "meeting_transcript",
      });
      setUploadedMemoId(memoId);
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      setImportPhase("done");
      await new Promise((r) => setTimeout(r, 600));
      toast.success("Memo created! Review your transcript and confirm to extract CRM fields.");
      navigate(ROUTES.MEMO_DETAIL(memoId));
    } catch {
      setImportPhase("idle");
      toast.error(uploadError || "Failed to import");
    }
  };

  return (
    <div className={`max-w-3xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
      <Link to={ROUTES.DASHBOARD} className={`inline-flex items-center gap-2 ${THEME_TOKENS.typography.capsLabel} text-muted-foreground/60 hover:text-beige mb-10 transition-colors group`}>
        <ArrowLeft className="h-3 w-3 group-hover:-translate-x-1 transition-transform" />
        Back to Dashboard
      </Link>

      <div className={V_PATTERNS.dashboardHeader + " text-center"}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          New <span className={THEME_TOKENS.typography.accentTitle}>Memo</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>
          Record a voice memo or import a meeting transcript.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className={`grid w-full grid-cols-2 mb-8 ${THEME_TOKENS.radius.card}`}>
          <TabsTrigger value="record" className="gap-2">
            <Mic className="h-4 w-4" />
            Record
          </TabsTrigger>
          <TabsTrigger value="import" className="gap-2">
            <FileText className="h-4 w-4" />
            Import transcript
          </TabsTrigger>
        </TabsList>

        <TabsContent value="record" className="mt-0">
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
        </TabsContent>

        <TabsContent value="import" className="mt-0">
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
            <p className={`${THEME_TOKENS.typography.capsLabel} mb-4`}>
              Paste meeting transcript
            </p>
            <p className="text-sm text-muted-foreground mb-6">
              From Zoom, Google Meet, Fireflies, Otter, or any meeting tool.
            </p>
            <textarea
              value={importTranscript}
              onChange={(e) => setImportTranscript(e.target.value)}
              placeholder="Paste your transcript here..."
              className="w-full min-h-[280px] rounded-2xl bg-secondary/[0.03] p-6 border border-border/20 text-sm leading-relaxed text-muted-foreground/90 font-medium tracking-tight whitespace-pre-wrap resize-y focus:outline-none focus:ring-2 focus:ring-beige/30 focus:border-beige/40 placeholder:text-muted-foreground/40 mb-6"
            />
            <Button
              variant="hero"
              disabled={isUploading || !importTranscript.trim()}
              onClick={handleImportSubmit}
              className="w-full rounded-full bg-beige text-cream"
            >
              {isUploading ? (
                <>
                  <span className="w-4 h-4 border-2 border-cream border-t-transparent rounded-full animate-spin mr-2" />
                  Processing...
                </>
              ) : (
                "Import & Continue"
              )}
            </Button>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default RecordPage;
