import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { Mic, Square, Upload, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

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
      // Simulate processing
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
      {/* Back Link */}
      <Link 
        to="/dashboard" 
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-8"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Dashboard
      </Link>

      {/* Recording Interface */}
      <div className="bg-card rounded-3xl shadow-medium p-8 text-center">
        {/* Status */}
        <p className="text-sm font-medium text-muted-foreground mb-4 uppercase tracking-wider">
          {getStatusText()}
        </p>

        {/* Waveform Circle */}
        <div className="relative w-64 h-64 mx-auto mb-8">
          {/* Outer ring animation when recording */}
          {state === "recording" && (
            <div className="absolute inset-0 rounded-full border-4 border-destructive/30 animate-ping" />
          )}
          
          {/* Main circle */}
          <div 
            className={`
              absolute inset-4 rounded-full flex items-center justify-center
              transition-all duration-300
              ${state === "recording" ? "bg-destructive/10" : "bg-secondary"}
              ${state === "processing" ? "animate-pulse" : ""}
            `}
          >
            {/* Waveform bars */}
            {state === "recording" && (
              <div className="absolute inset-0 flex items-center justify-center">
                {Array.from({ length: 24 }).map((_, i) => {
                  const angle = (i / 24) * 360;
                  return (
                    <div
                      key={i}
                      className="absolute w-1 bg-destructive/60 rounded-full"
                      style={{
                        height: `${20 + Math.random() * 40}%`,
                        transform: `rotate(${angle}deg) translateY(-50%)`,
                        animation: `waveform 0.8s ease-in-out ${i * 0.05}s infinite`,
                      }}
                    />
                  );
                })}
              </div>
            )}

            {/* Timer */}
            <div className="relative z-10 text-4xl font-bold text-foreground">
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
          className={`
            rounded-full mx-auto
            ${state === "recording" ? "animate-pulse" : ""}
          `}
        >
          {state === "recording" ? (
            <Square className="h-8 w-8" />
          ) : (
            <Mic className="h-8 w-8" />
          )}
        </Button>

        <p className="text-sm text-muted-foreground mt-4">
          {state === "idle" && "Tap to start recording"}
          {state === "recording" && "Tap to stop"}
          {state === "processing" && "This usually takes 30 seconds"}
        </p>

        {/* Upload Option */}
        {state === "idle" && (
          <div className="mt-8 pt-8 border-t border-border">
            <p className="text-sm text-muted-foreground mb-4">Or upload an audio file</p>
            <div className="border-2 border-dashed border-border rounded-2xl p-8 hover:border-primary/50 transition-colors cursor-pointer">
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
