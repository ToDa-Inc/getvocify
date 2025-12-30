import { useEffect, useState, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Mic, Square, Upload, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useMediaRecorder, useAudioUpload } from "@/features/recording";
import {
  AudioWaveform,
  AudioPreview,
  UploadProgress,
  RecordingError,
} from "@/features/recording/components";
import { AUDIO, ROUTES } from "@/shared/lib/constants";
import { isSupportedAudioType, formatFileSize } from "@/features/recording/types";
import { toast } from "sonner";

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

const RecordPage = () => {
  const navigate = useNavigate();
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

  // Handle upload success
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
      await start();
    } else if (state === "recording") {
      stop();
    }
  };

  const handleUpload = async () => {
    if (!audio) return;

    try {
      const memoId = await upload(audio);
      setUploadedMemoId(memoId);
      // Navigation happens in useEffect when progress.complete
    } catch (err) {
      toast.error(uploadError || "Failed to upload audio");
    }
  };

  const handleFileSelect = async (file: File) => {
    // Validate file type
    if (!isSupportedAudioType(file)) {
      toast.error("Unsupported file type. Please use MP3, WAV, or M4A.");
      return;
    }

    // Validate file size
    if (file.size > AUDIO.MAX_FILE_SIZE_BYTES) {
      toast.error(`File too large. Maximum size is ${formatFileSize(AUDIO.MAX_FILE_SIZE_BYTES)}`);
      return;
    }

    // Create RecordedAudio object
    const audioUrl = URL.createObjectURL(file);
    const audioBlob = file;

    // Estimate duration (rough: 1MB ≈ 1 minute for compressed audio)
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
    if (file) {
      handleFileSelect(file);
    }
    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleDropzoneClick = () => {
    fileInputRef.current?.click();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) {
      handleFileSelect(file);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleReRecord = () => {
    cancel();
    resetUpload();
  };

  const handleErrorRetry = () => {
    reset();
    resetUpload();
    start();
  };

  const handleErrorReset = () => {
    reset();
    resetUpload();
  };

  const getStatusText = () => {
    switch (state) {
      case "idle":
        return "Ready to record";
      case "requesting":
        return "Requesting microphone access...";
      case "recording":
        return "Recording...";
      case "stopped":
        return "Recording complete";
      case "uploading":
        return "Uploading...";
      case "error":
        return "Error occurred";
      default:
        return "";
    }
  };

  // Error state
  if (state === "error" && error) {
    return (
      <div className="max-w-2xl mx-auto animate-fade-in">
        <Link
          to={ROUTES.DASHBOARD}
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-8"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>

        <div className="bg-card rounded-3xl shadow-medium p-12">
          <RecordingError
            error={error}
            onRetry={handleErrorRetry}
            onReset={handleErrorReset}
          />
        </div>
      </div>
    );
  }

  // Uploading state
  if (isUploading && progress) {
    return (
      <div className="max-w-2xl mx-auto animate-fade-in">
        <Link
          to={ROUTES.DASHBOARD}
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-8"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>

        <div className="bg-card rounded-3xl shadow-medium p-12 text-center">
          <p className="text-sm font-medium mb-6 uppercase tracking-wider text-muted-foreground">
            {getStatusText()}
          </p>

          <div className="relative w-48 h-48 mx-auto mb-8 rounded-full bg-secondary flex items-center justify-center">
            <div className="flex flex-col items-center gap-4">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              <div className="text-4xl font-bold text-foreground">
                {formatTime(duration)}
              </div>
            </div>
          </div>

          <UploadProgress progress={progress} className="mb-4" />

          <p className="text-sm text-muted-foreground">
            This usually takes 30 seconds
          </p>
        </div>
      </div>
    );
  }

  // Preview state (stopped, ready to upload)
  if (state === "stopped" && audio) {
    return (
      <div className="max-w-2xl mx-auto animate-fade-in">
        <Link
          to={ROUTES.DASHBOARD}
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-8"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>

        <div className="bg-card rounded-3xl shadow-medium p-12">
          <p className="text-sm font-medium mb-6 uppercase tracking-wider text-muted-foreground text-center">
            {getStatusText()}
          </p>

          <AudioPreview
            audio={audio}
            onReRecord={handleReRecord}
            onUpload={handleUpload}
          />
        </div>
      </div>
    );
  }

  // Recording or idle state
  return (
    <div className="max-w-2xl mx-auto animate-fade-in">
      <Link
        to={ROUTES.DASHBOARD}
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-8"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Dashboard
      </Link>

      <div className="bg-card rounded-3xl shadow-medium p-12 text-center">
        {/* Status */}
        <p
          className={`text-sm font-medium mb-6 uppercase tracking-wider transition-colors ${
            state === "recording"
              ? "text-destructive"
              : "text-muted-foreground"
          }`}
        >
          {getStatusText()}
        </p>

        {/* Waveform visualization */}
        <div className="relative w-48 h-48 mx-auto mb-8 rounded-full bg-secondary flex items-center justify-center">
          {/* Recording ring */}
          {state === "recording" && (
            <>
              <div className="absolute inset-0 rounded-full border-4 border-destructive/40 animate-ping" />
              <div className="absolute inset-0 rounded-full border-2 border-destructive/60" />
            </>
          )}

          {/* Inner content */}
          <div className="flex flex-col items-center gap-4">
            <AudioWaveform
              visualization={visualization}
              isRecording={state === "recording"}
            />

            {/* Timer */}
            <div
              className={`text-4xl font-bold transition-colors ${
                state === "recording" ? "text-destructive" : "text-foreground"
              }`}
            >
              {formatTime(duration)}
            </div>
          </div>
        </div>

        {/* Record Button */}
        <Button
          variant={state === "recording" ? "destructive" : "default"}
          size="lg"
          onClick={handleRecordClick}
          disabled={state === "requesting"}
          className="rounded-full mx-auto"
        >
          {state === "requesting" ? (
            <div className="w-6 h-6 border-2 border-cream border-t-transparent rounded-full animate-spin" />
          ) : state === "recording" ? (
            <>
              <Square className="h-5 w-5 mr-2" />
              Stop Recording
            </>
          ) : (
            <>
              <Mic className="h-5 w-5 mr-2" />
              Start Recording
            </>
          )}
        </Button>

        <p className="text-sm text-muted-foreground mt-4">
          {state === "idle" && "Tap to start recording"}
          {state === "recording" && "Tap to stop"}
          {state === "requesting" && "Please allow microphone access"}
        </p>

        {/* Upload Option */}
        {state === "idle" && (
          <div className="mt-10 pt-8 border-t border-border">
            <p className="text-sm text-muted-foreground mb-4">
              Or upload an audio file
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*"
              onChange={handleFileInputChange}
              className="hidden"
            />
            <div
              onClick={handleDropzoneClick}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              className="border-2 border-dashed border-border rounded-2xl p-8 hover:border-primary/50 transition-colors cursor-pointer"
            >
              <Upload className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
              <p className="text-sm font-medium text-foreground">
                Drop your file here or click to browse
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                MP3, WAV, M4A (up to {formatFileSize(AUDIO.MAX_FILE_SIZE_BYTES)})
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default RecordPage;
