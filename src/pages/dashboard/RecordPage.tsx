import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { Mic, Square, Upload, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import SimpleWaveform from "@/components/dashboard/SimpleWaveform";

type RecordingState = "idle" | "recording" | "processing";

const RecordPage = () => {
  const [state, setState] = useState<RecordingState>("idle");
  const [seconds, setSeconds] = useState(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (state === "recording") {
      timerRef.current = setInterval(() => {
        setSeconds((s) => s + 1);
      }, 1000);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [state]);

  const formatTime = (s: number) => {
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const handleRecordClick = () => {
    if (state === "idle") {
      setState("recording");
      setSeconds(0);
    } else if (state === "recording") {
      setState("processing");
      setTimeout(() => {
        window.location.href = "/dashboard/memos/new";
      }, 2000);
    }
  };

  const getStatusText = () => {
    switch (state) {
      case "idle":
        return "Ready to record";
      case "recording":
        return "Recording...";
      case "processing":
        return "Processing...";
    }
  };

  return (
    <div className="max-w-2xl mx-auto animate-fade-in">
      <Link 
        to="/dashboard" 
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-8"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Dashboard
      </Link>

      <div className="bg-card rounded-3xl shadow-medium p-12 text-center">
        {/* Status */}
        <p className={`text-sm font-medium mb-6 uppercase tracking-wider transition-colors ${
          state === "recording" ? "text-destructive" : "text-muted-foreground"
        }`}>
          {getStatusText()}
        </p>

        {/* Simple waveform visualization */}
        <div className="relative w-48 h-48 mx-auto mb-8 rounded-full bg-secondary flex items-center justify-center">
          {/* Recording ring */}
          {state === "recording" && (
            <div className="absolute inset-0 rounded-full border-4 border-destructive/40 animate-ping" />
          )}
          {state === "recording" && (
            <div className="absolute inset-0 rounded-full border-2 border-destructive/60" />
          )}
          
          {/* Inner content */}
          <div className="flex flex-col items-center gap-4">
            <SimpleWaveform 
              isRecording={state === "recording"} 
              isProcessing={state === "processing"} 
            />
            
            {/* Timer */}
            <div className={`text-4xl font-bold transition-colors ${
              state === "recording" ? "text-destructive" : "text-foreground"
            }`}>
              {formatTime(seconds)}
            </div>
          </div>
        </div>

        {/* Record Button */}
        <Button
          variant={state === "recording" ? "recording" : "hero"}
          size="icon-xl"
          onClick={handleRecordClick}
          disabled={state === "processing"}
          className="rounded-full mx-auto"
        >
          {state === "recording" ? (
            <Square className="h-6 w-6" />
          ) : state === "processing" ? (
            <div className="w-6 h-6 border-2 border-cream border-t-transparent rounded-full animate-spin" />
          ) : (
            <Mic className="h-6 w-6" />
          )}
        </Button>

        <p className="text-sm text-muted-foreground mt-4">
          {state === "idle" && "Tap to start recording"}
          {state === "recording" && "Tap to stop"}
          {state === "processing" && "This usually takes 30 seconds"}
        </p>

        {/* Upload Option */}
        {state === "idle" && (
          <div className="mt-10 pt-8 border-t border-border">
            <p className="text-sm text-muted-foreground mb-4">Or upload an audio file</p>
            <div className="border-2 border-dashed border-border rounded-2xl p-8 hover:border-beige/50 transition-colors cursor-pointer">
              <Upload className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
              <p className="text-sm font-medium text-foreground">
                Drop your file here or click to browse
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                MP3, WAV, M4A (up to 10MB)
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default RecordPage;
