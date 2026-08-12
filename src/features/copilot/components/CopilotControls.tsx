import { Mic, Square, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface CopilotControlsProps {
  isListening: boolean;
  isConnected: boolean;
  isBusy?: boolean;
  onToggle: () => void;
}

export function CopilotControls({
  isListening,
  isConnected,
  isBusy,
  onToggle,
}: CopilotControlsProps) {
  return (
    <div className="flex flex-col items-center gap-3">
      <Button
        size="lg"
        onClick={onToggle}
        className={`h-16 px-10 rounded-full text-base font-black tracking-tight shadow-medium ${
          isListening
            ? "bg-red-500 hover:bg-red-600 text-white"
            : "bg-beige hover:bg-beige/90 text-cream"
        }`}
      >
        {isListening ? (
          <>
            <Square className="mr-2 h-5 w-5 fill-current" />
            Stop listening
          </>
        ) : (
          <>
            <Mic className="mr-2 h-5 w-5" />
            Start listening
          </>
        )}
      </Button>
      <div className="flex items-center gap-2 text-xs font-bold text-muted-foreground">
        {isListening ? (
          <>
            <span
              className={`h-2 w-2 rounded-full ${
                isConnected ? "bg-emerald-500 animate-pulse" : "bg-amber-400"
              }`}
            />
            {isConnected ? "Live transcription" : "Connecting…"}
            {isBusy && (
              <span className="inline-flex items-center gap-1 text-beige">
                <Loader2 className="h-3 w-3 animate-spin" />
                coaching
              </span>
            )}
          </>
        ) : (
          <span>Phone on speaker · laptop mic · silent coaching</span>
        )}
      </div>
    </div>
  );
}
