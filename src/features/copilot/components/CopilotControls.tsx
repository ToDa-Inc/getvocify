import { Mic, Square } from "lucide-react";
import { VocifySpinner } from "@/components/ui/vocify-loader";
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
        className={`h-12 px-8 rounded-lg text-base font-semibold ${
          isListening
            ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
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
                isConnected ? "bg-success animate-pulse" : "bg-warning"
              }`}
            />
            {isConnected ? "Live transcription" : "Connecting…"}
            {isBusy && (
              <span className="inline-flex items-center gap-1 text-beige">
                <VocifySpinner size={12} />
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
