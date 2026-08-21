import { useState, useRef, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { 
  Mic, 
  Square, 
  Upload, 
  FileText, 
  RotateCcw, 
  ChevronDown, 
  ChevronUp, 
  Sparkles, 
  X 
} from "lucide-react";
import { Button } from "@/components/ui/button";
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
import { memoKeys } from "@/features/memos/api";
import { AUDIO } from "@/shared/lib/constants";
import { isSupportedAudioType, formatFileSize } from "@/features/recording/types";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

export interface VoiceRecorderWidgetProps {
  /** Callback fired with the created memo ID when recording/import succeeds */
  onComplete: (memoId: string) => void;
  /** Optional container CSS class */
  className?: string;
}

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

export const VoiceRecorderWidget = ({
  onComplete,
  className = "",
}: VoiceRecorderWidgetProps) => {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isSubmitLocked = useRef(false);

  // Local UI state
  const [isPasteOpen, setIsPasteOpen] = useState(false);
  const [pastedTranscript, setPastedTranscript] = useState("");
  const [editedTranscript, setEditedTranscript] = useState("");
  const [isDragging, setIsDragging] = useState(false);

  const {
    state,
    duration,
    error: recorderError,
    audio,
    visualization,
    start: startRecording,
    stop: stopRecording,
    cancel: cancelRecording,
    reset: resetRecording,
  } = useMediaRecorder();

  const {
    upload,
    uploadTranscriptOnly,
    uploadTranscriptAndExtract,
    progress,
    isUploading,
    error: uploadError,
    reset: resetUpload,
  } = useAudioUpload();

  const {
    isTranscribing,
    isConnected,
    finalTranscript,
    interimTranscript,
    fullTranscript,
    start: startTranscription,
    stop: stopTranscription,
    reset: resetTranscription,
  } = useRealtimeTranscription(
    user?.id || "anonymous",
    "multi"
  );

  // Synchronize fullTranscript to editable buffer when streaming or stopped
  useEffect(() => {
    if (fullTranscript) {
      setEditedTranscript(fullTranscript);
    }
  }, [fullTranscript]);

  // Handle start/stop recording button
  const handleRecordToggle = async () => {
    if (state === "idle") {
      try {
        const stream = await startRecording();
        if (stream) {
          await startTranscription(stream);
        }
      } catch {
        toast.error("Could not access microphone. Please check permissions.");
      }
    } else if (state === "recording") {
      stopRecording();
      stopTranscription();
    }
  };

  // Re-record / reset state
  const handleReRecord = () => {
    cancelRecording();
    resetUpload();
    resetTranscription();
    setEditedTranscript("");
    isSubmitLocked.current = false;
  };

  // Error retry
  const handleErrorRetry = async () => {
    resetRecording();
    resetUpload();
    resetTranscription();
    try {
      const stream = await startRecording();
      if (stream) {
        await startTranscription(stream);
      }
    } catch {
      toast.error("Microphone retry failed. Check device permissions.");
    }
  };

  // Error reset
  const handleErrorReset = () => {
    resetRecording();
    resetUpload();
    resetTranscription();
    isSubmitLocked.current = false;
  };

  // Submit reviewed transcript (Step 1 -> extraction)
  const handleAcceptTranscript = async () => {
    if (isSubmitLocked.current) return;
    const textToSubmit = editedTranscript.trim() || fullTranscript.trim();
    if (!textToSubmit) {
      toast.error("Transcript cannot be empty");
      return;
    }

    isSubmitLocked.current = true;
    try {
      const memoId = await uploadTranscriptAndExtract(textToSubmit);
      resetTranscription();
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      toast.success("Memo created! AI is extracting CRM fields...");
      onComplete(memoId);
    } catch {
      isSubmitLocked.current = false;
      toast.error(uploadError || "Failed to create memo from transcript");
    }
  };

  // Fallback upload when no live transcript exists but audio blob was recorded
  const handleUploadAudio = async () => {
    if (!audio) return;
    try {
      const memoId = await upload(audio);
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      toast.success("Recording uploaded! AI is transcribing and extracting fields...");
      onComplete(memoId);
    } catch {
      toast.error(uploadError || "Failed to upload audio recording");
    }
  };

  // Import pasted meeting transcript
  const handleImportPastedTranscript = async () => {
    const trimmed = pastedTranscript.trim();
    if (!trimmed) {
      toast.error("Please paste a transcript before importing");
      return;
    }

    if (isSubmitLocked.current) return;
    isSubmitLocked.current = true;

    try {
      const memoId = await uploadTranscriptOnly(trimmed, {
        sourceType: "meeting_transcript",
      });
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      toast.success("Transcript imported! Reviewing details...");
      setPastedTranscript("");
      setIsPasteOpen(false);
      onComplete(memoId);
    } catch {
      isSubmitLocked.current = false;
      toast.error(uploadError || "Failed to import transcript");
    }
  };

  // File drop / upload handling
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
    const estimatedDuration = (file.size / (1024 * 1024)) * 60;

    try {
      const memoId = await upload({
        blob: file,
        url: audioUrl,
        duration: estimatedDuration,
        mimeType: file.type,
        size: file.size,
      });
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      toast.success("Audio uploaded! Processing your memo...");
      onComplete(memoId);
    } catch {
      URL.revokeObjectURL(audioUrl);
      toast.error(uploadError || "Failed to upload audio file");
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  // Determine sub-views
  const hasTranscript = Boolean(fullTranscript?.trim() || editedTranscript.trim());
  const showReviewStep = state === "stopped" && (hasTranscript || audio);

  // 1. Error state
  if (state === "error" && recorderError) {
    return (
      <div className={cn(`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.container} p-8 text-center`, className)}>
        <RecordingError
          error={recorderError}
          onRetry={handleErrorRetry}
          onReset={handleErrorReset}
        />
      </div>
    );
  }

  // 2. Uploading / Processing state
  if (isUploading && progress) {
    return (
      <div className={cn(`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-10 text-center`, className)}>
        <div className="relative w-28 h-28 mx-auto mb-6 rounded-full bg-secondary/30 flex items-center justify-center">
          <div className="w-10 h-10 border-2 border-beige border-t-transparent rounded-full animate-spin" />
        </div>
        <h3 className="text-lg font-semibold text-foreground mb-1">
          Processing your memo...
        </h3>
        <p className="text-xs text-muted-foreground mb-6">
          Uploading audio & initiating AI CRM extraction
        </p>
        <div className="max-w-md mx-auto">
          <UploadProgress progress={progress} className="mb-3" />
        </div>
      </div>
    );
  }

  // 3. Transcript Ready / Review Step (Step 1)
  if (showReviewStep) {
    return (
      <div className={cn(`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.container} p-6 md:p-8 text-left`, className)}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-beige" />
            <h3 className="text-base font-semibold text-foreground">Review Transcript</h3>
          </div>
          {hasTranscript && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-success/10 text-success border border-success/20">
              Live STT
            </span>
          )}
        </div>

        <p className="text-xs text-muted-foreground mb-4">
          {hasTranscript
            ? "Review and edit your spoken notes before confirming extraction."
            : "No real-time text was generated. You can upload the audio for full server-side transcription."}
        </p>

        {hasTranscript ? (
          <div className="space-y-4">
            <textarea
              value={editedTranscript}
              onChange={(e) => setEditedTranscript(e.target.value)}
              placeholder="Edit your transcript..."
              className="w-full min-h-[220px] rounded-xl bg-secondary/30 p-4 border border-border/80 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground/60 resize-y focus:outline-none focus:ring-2 focus:ring-beige/40 focus:border-beige/50"
            />
            <div className="flex flex-col sm:flex-row gap-3 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={handleReRecord}
                disabled={isUploading}
                className="flex-1 rounded-full gap-2"
              >
                <RotateCcw className="h-4 w-4" />
                Re-record
              </Button>
              <Button
                type="button"
                variant="hero"
                disabled={isUploading || !editedTranscript.trim()}
                onClick={handleAcceptTranscript}
                className="flex-1 rounded-full bg-beige text-cream hover:bg-beige/90 font-medium"
              >
                {isUploading ? (
                  <>
                    <span className="w-4 h-4 border-2 border-cream border-t-transparent rounded-full animate-spin mr-2" />
                    Extracting...
                  </>
                ) : (
                  "Accept & Continue"
                )}
              </Button>
            </div>
          </div>
        ) : audio ? (
          <AudioPreview
            audio={audio}
            onReRecord={handleReRecord}
            onUpload={handleUploadAudio}
          />
        ) : null}
      </div>
    );
  }

  // 4. Recording Active State
  if (state === "recording") {
    return (
      <div className={cn(`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-8 md:p-10 text-center`, className)}>
        {/* Status indicator */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-destructive/10 text-destructive text-xs font-medium border border-destructive/20 mb-6 animate-pulse">
          <span className="w-2 h-2 rounded-full bg-destructive" />
          Recording...
        </div>

        {/* Dynamic Waveform & Timer Orb */}
        <div className="relative w-40 h-40 md:w-48 md:h-48 mx-auto mb-6 rounded-full bg-secondary/40 flex items-center justify-center border border-border/60">
          <div className="absolute inset-0 rounded-full border-4 border-destructive/20 animate-ping" />
          <div className="absolute inset-0 rounded-full border-2 border-destructive/40" />

          <div className="flex flex-col items-center gap-4 relative z-10">
            <AudioWaveform
              visualization={visualization}
              isRecording={true}
              bars={11}
            />
            <div className="text-3xl md:text-4xl font-semibold tracking-tight tabular-nums text-destructive">
              {formatTime(duration)}
            </div>
          </div>
        </div>

        {/* Live streaming transcript */}
        <div className="max-w-xl mx-auto mb-8 text-left">
          <LiveTranscript
            finalTranscript={finalTranscript}
            interimTranscript={interimTranscript}
            isActive={isTranscribing && isConnected}
          />
        </div>

        {/* Stop recording action */}
        <Button
          type="button"
          variant="destructive"
          size="xl"
          onClick={handleRecordToggle}
          className="rounded-full px-8 gap-2 shadow-md hover:scale-105 active:scale-95 transition-transform"
        >
          <Square className="h-4 w-4 fill-current" />
          Stop recording
        </Button>
      </div>
    );
  }

  // 5. Idle / Default State
  return (
    <div className={cn(`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-8 md:p-10 text-center`, className)}>
      {/* Circular Record Core */}
      <div className="flex flex-col items-center justify-center mb-6">
        <button
          type="button"
          onClick={handleRecordToggle}
          disabled={state === "requesting"}
          aria-label="Start recording voice memo"
          className={cn(
            "group relative w-20 h-20 rounded-full glass-panel border border-white/70 shadow-lg flex items-center justify-center",
            "hover:scale-105 hover:border-beige/40 active:scale-95 transition-all duration-200 cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-beige"
          )}
        >
          {state === "requesting" ? (
            <div className="w-6 h-6 border-2 border-beige border-t-transparent rounded-full animate-spin" />
          ) : (
            <div className="w-7 h-7 rounded-full bg-beige group-hover:scale-110 transition-transform duration-200 shadow-xs flex items-center justify-center text-cream">
              <Mic className="h-4 w-4 text-cream" />
            </div>
          )}
        </button>

        <span className="text-sm font-medium text-foreground mt-3">
          {state === "requesting" ? "Requesting microphone..." : "Record"}
        </span>
        <span className="text-xs text-muted-foreground mt-0.5">
          Tap to record or import transcript
        </span>
      </div>

      {/* Quick Actions Row */}
      <div className="flex items-center justify-center gap-3 mb-6">
        <button
          type="button"
          onClick={() => setIsPasteOpen((prev) => !prev)}
          className={cn(
            "inline-flex items-center gap-1.5 px-4 py-2 rounded-full border text-xs font-medium transition-all cursor-pointer",
            isPasteOpen
              ? "border-beige/40 bg-beige/10 text-beige"
              : "border-border/70 bg-card hover:bg-secondary/40 text-foreground hover:border-beige/30"
          )}
        >
          <FileText className="h-3.5 w-3.5 text-beige" />
          <span>Paste transcript</span>
          {isPasteOpen ? (
            <ChevronUp className="h-3 w-3 ml-0.5 opacity-60" />
          ) : (
            <ChevronDown className="h-3 w-3 ml-0.5 opacity-60" />
          )}
        </button>
      </div>

      {/* Collapsible Paste Section */}
      {isPasteOpen && (
        <div className="mb-6 p-5 rounded-xl bg-card border border-border/80 text-left animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-foreground">Paste Meeting Transcript</span>
            <button
              type="button"
              onClick={() => setIsPasteOpen(false)}
              className="text-muted-foreground hover:text-foreground p-1 rounded-md"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
            From Zoom, Google Meet, Microsoft Teams, Fireflies, Otter, or notes.
          </p>
          <textarea
            value={pastedTranscript}
            onChange={(e) => setPastedTranscript(e.target.value)}
            placeholder="Paste your transcript text here..."
            className="w-full min-h-[140px] rounded-lg bg-secondary/30 p-3.5 border border-border/60 text-xs leading-relaxed text-foreground placeholder:text-muted-foreground/50 resize-y focus:outline-none focus:ring-2 focus:ring-beige/30 focus:border-beige/40 mb-3"
          />
          <div className="flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setPastedTranscript("");
                setIsPasteOpen(false);
              }}
              className="text-xs rounded-full h-8 px-3"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="hero"
              size="sm"
              disabled={isUploading || !pastedTranscript.trim()}
              onClick={handleImportPastedTranscript}
              className="text-xs rounded-full h-8 px-4 bg-beige text-cream hover:bg-beige/90"
            >
              {isUploading ? "Importing..." : "Import & Continue"}
            </Button>
          </div>
        </div>
      )}

      {/* Audio File Dropzone */}
      <input
        ref={fileInputRef}
        type="file"
        accept="audio/*"
        onChange={handleFileInputChange}
        className="hidden"
      />

      <div
        onClick={() => fileInputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={cn(
          "border border-dashed rounded-xl p-5 transition-all duration-150 cursor-pointer flex items-center justify-center gap-4 text-left group",
          isDragging
            ? "border-beige bg-beige/5"
            : "border-border/70 hover:border-beige/30 bg-secondary/15 hover:bg-secondary/30"
        )}
      >
        <div className="w-10 h-10 rounded-xl bg-beige/10 flex items-center justify-center flex-shrink-0 group-hover:scale-105 transition-transform">
          <Upload className="h-5 w-5 text-beige" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-foreground group-hover:text-beige transition-colors">
            Drop an audio recording here, or browse
          </p>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            MP3, WAV, M4A up to {formatFileSize(AUDIO.MAX_FILE_SIZE_BYTES)}
          </p>
        </div>
      </div>
    </div>
  );
};

export default VoiceRecorderWidget;
