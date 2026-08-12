import { useCallback, useRef, useState } from "react";
import { streamObjectionSuggestion } from "../api/suggest";
import type {
  CallMode,
  ObjectionSuggestion,
  SuggestRequest,
} from "../types";

export interface UseObjectionSuggestionsReturn {
  suggestion: ObjectionSuggestion | null;
  rawStream: string;
  isLoading: boolean;
  error: string | null;
  latencyMs: number | null;
  model: string | null;
  lastTurn: string | null;
  requestSuggestion: (input: {
    latestTurn: string;
    transcriptWindow: string;
    productContext?: string;
    language?: SuggestRequest["language"];
    callMode?: CallMode;
    speakerRole?: SuggestRequest["speaker_role"];
    /** Bypass same-turn dedupe (e.g. manual Coach now) */
    force?: boolean;
  }) => void;
  clear: () => void;
}

export function useObjectionSuggestions(): UseObjectionSuggestionsReturn {
  const [suggestion, setSuggestion] = useState<ObjectionSuggestion | null>(null);
  const [rawStream, setRawStream] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [lastTurn, setLastTurn] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const lastKeyRef = useRef("");

  const clear = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setSuggestion(null);
    setRawStream("");
    setIsLoading(false);
    setError(null);
    setLatencyMs(null);
    setModel(null);
    setLastTurn(null);
    lastKeyRef.current = "";
  }, []);

  const requestSuggestion = useCallback(
    (input: {
      latestTurn: string;
      transcriptWindow: string;
      productContext?: string;
      language?: SuggestRequest["language"];
      callMode?: CallMode;
      speakerRole?: SuggestRequest["speaker_role"];
      force?: boolean;
    }) => {
      const key = input.latestTurn.trim().toLowerCase();
      if (!key) return;
      if (!input.force && key === lastKeyRef.current) return;
      lastKeyRef.current = key;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setIsLoading(true);
      setError(null);
      setRawStream("");
      setSuggestion(null);
      setLastTurn(input.latestTurn);
      setLatencyMs(null);
      setModel(null);

      void streamObjectionSuggestion(
        {
          transcript_window: input.transcriptWindow.slice(-6000),
          latest_turn: input.latestTurn,
          product_context: input.productContext,
          language: input.language ?? "auto",
          call_mode: input.callMode ?? "speakerphone",
          speaker_role: input.speakerRole ?? "unknown",
        },
        (event) => {
          if (controller.signal.aborted) return;
          if (event.type === "token") {
            setRawStream((prev) => prev + event.text);
          } else if (event.type === "result") {
            setSuggestion(event.suggestion);
            setLatencyMs(event.latency_ms);
            setModel(event.model);
            setIsLoading(false);
          } else if (event.type === "error") {
            setError(event.message);
            setIsLoading(false);
          } else if (event.type === "done") {
            setIsLoading(false);
          }
        },
        controller.signal
      ).catch((err: unknown) => {
        if ((err as { name?: string })?.name === "AbortError") return;
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Suggestion failed");
        setIsLoading(false);
      });
    },
    []
  );

  return {
    suggestion,
    rawStream,
    isLoading,
    error,
    latencyMs,
    model,
    lastTurn,
    requestSuggestion,
    clear,
  };
}
