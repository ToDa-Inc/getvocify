import { useCallback, useEffect, useState } from "react";
import { Headphones, Sparkles } from "lucide-react";
import { useAuth } from "@/features/auth";
import { useRealtimeTranscription } from "@/features/recording";
import {
  CopilotControls,
  DEFAULT_PRODUCT_CONTEXT,
  PRODUCT_CONTEXT_STORAGE_KEY,
  SuggestionCard,
  VoiceEnrollmentPanel,
  useObjectionSuggestions,
  useTurnDetector,
  type TurnMeta,
} from "@/features/copilot";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

const ObjectionCopilotPage = () => {
  const { user } = useAuth();
  const [productContext, setProductContext] = useState(() => {
    try {
      return localStorage.getItem(PRODUCT_CONTEXT_STORAGE_KEY) || DEFAULT_PRODUCT_CONTEXT;
    } catch {
      return DEFAULT_PRODUCT_CONTEXT;
    }
  });
  const [showContext, setShowContext] = useState(false);
  const [voiceEnrolled, setVoiceEnrolled] = useState(false);

  const {
    isTranscribing,
    isConnected,
    error: transcriptionError,
    finalTranscript,
    interimTranscript,
    fullTranscript,
    finalWords,
    endOfUtteranceSeq,
    forceEndOfUtterance,
    start: startTranscription,
    stop: stopTranscription,
    reset: resetTranscription,
  } = useRealtimeTranscription(user?.id || "anonymous", "multi", {
    mode: voiceEnrolled ? "copilot" : "default",
  });

  const {
    suggestion,
    rawStream,
    isLoading,
    error: suggestError,
    latencyMs,
    model,
    lastTurn,
    requestSuggestion,
    clear: clearSuggestion,
  } = useObjectionSuggestions();

  useEffect(() => {
    try {
      localStorage.setItem(PRODUCT_CONTEXT_STORAGE_KEY, productContext);
    } catch {
      /* ignore */
    }
  }, [productContext]);

  const handleTurn = useCallback(
    (latestTurn: string, fullFinal: string, meta: TurnMeta) => {
      requestSuggestion({
        latestTurn,
        transcriptWindow: fullFinal,
        productContext,
        language: "auto",
        callMode: "speakerphone",
        speakerRole: voiceEnrolled ? meta.speakerRole : "unknown",
      });
    },
    [productContext, requestSuggestion, voiceEnrolled]
  );

  useTurnDetector({
    finalTranscript,
    interimTranscript,
    enabled: isTranscribing,
    endOfUtteranceSeq,
    settleMs: 900,
    minWords: 6,
    finalWords,
    repLabel: "Salesperson",
    gateRepTurns: voiceEnrolled,
    onTurn: handleTurn,
  });

  const handleToggle = async () => {
    if (isTranscribing) {
      stopTranscription();
      return;
    }
    clearSuggestion();
    await startTranscription();
  };

  const handleReset = () => {
    stopTranscription();
    resetTranscription();
    clearSuggestion();
  };

  const handleCoachNow = () => {
    forceEndOfUtterance();
    const source = (interimTranscript || finalTranscript).trim();
    if (!source) return;
    const windowText = fullTranscript.trim() || source;
    const chunks = windowText.split(/(?<=[.!?…])\s+/).filter(Boolean);
    const latestTurn = (chunks[chunks.length - 1] || source).trim();
    requestSuggestion({
      latestTurn,
      transcriptWindow: windowText,
      productContext,
      language: "auto",
      callMode: "speakerphone",
      speakerRole: "unknown",
      force: true,
    });
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-16">
      <header className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-beige/15 px-3 py-1 text-[10px] font-medium text-beige border border-beige/20">
            <Sparkles className="h-3 w-3" />
            Beta
          </span>
          <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            Call Copilot
          </span>
        </div>
        <h1 className="text-3xl md:text-4xl font-semibold tracking-tight text-foreground flex items-center gap-3">
          <Headphones className="h-8 w-8 text-beige" />
          Real-time objection handling
        </h1>
        <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
          Put your phone on speaker. Hit listen. When the prospect finishes objecting, you get
          the exact words to say — silently on screen.
          {voiceEnrolled
            ? " Your enrolled voice is used so we mostly coach on prospect turns."
            : " Record a short voice sample below so we can tell you from the prospect."}
        </p>
      </header>

      {user?.id && (
        <VoiceEnrollmentPanel
          userId={user.id}
          onEnrollmentChange={setVoiceEnrolled}
        />
      )}

      <div className="flex flex-col items-center gap-3">
        <CopilotControls
          isListening={isTranscribing}
          isConnected={isConnected}
          isBusy={isLoading}
          onToggle={handleToggle}
        />
        <Button
          variant="outline"
          size="sm"
          className="rounded-full text-xs font-bold"
          onClick={handleCoachNow}
          disabled={!fullTranscript.trim() || isLoading}
        >
          Coach now
        </Button>
        {!voiceEnrolled && (
          <p className="text-[11px] text-muted-foreground text-center max-w-sm">
            Without a voice sample, coaching may fire on your own speech too — use Coach now
            when needed.
          </p>
        )}
      </div>

      {(transcriptionError || suggestError) && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {transcriptionError || suggestError}
        </div>
      )}

      <SuggestionCard
        suggestion={suggestion}
        isLoading={isLoading}
        rawStream={rawStream}
        lastTurn={lastTurn}
        latencyMs={latencyMs}
        model={model}
      />

      <section className="rounded-3xl border border-border/40 bg-white/70 p-5 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-xs font-medium text-muted-foreground">
            Live transcript
          </h2>
          <Button variant="ghost" size="sm" className="text-xs" onClick={handleReset}>
            Reset
          </Button>
        </div>
        <div className="min-h-[120px] max-h-56 overflow-y-auto rounded-2xl bg-cream/60 p-4 text-sm leading-relaxed">
          {fullTranscript ? (
            <p>
              <span className="text-foreground">{finalTranscript}</span>
              {interimTranscript && (
                <span className="text-muted-foreground/70"> {interimTranscript}</span>
              )}
            </p>
          ) : (
            <p className="text-muted-foreground text-xs">
              Transcript appears here as the room is heard…
            </p>
          )}
        </div>
      </section>

      <section className="rounded-3xl border border-border/40 bg-white/70 p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-medium text-muted-foreground">
            Offer context
          </h2>
          <Button
            variant="ghost"
            size="sm"
            className="text-xs"
            onClick={() => setShowContext((v) => !v)}
          >
            {showContext ? "Hide" : "Edit"}
          </Button>
        </div>
        {showContext ? (
          <Textarea
            value={productContext}
            onChange={(e) => setProductContext(e.target.value)}
            rows={8}
            className="text-sm rounded-2xl"
            placeholder="Your offer, ICP, proof points…"
          />
        ) : (
          <p className="text-xs text-muted-foreground line-clamp-3 whitespace-pre-wrap">
            {productContext}
          </p>
        )}
      </section>
    </div>
  );
};

export default ObjectionCopilotPage;
