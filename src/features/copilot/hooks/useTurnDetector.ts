import { useEffect, useRef } from "react";
import type { TranscriptWord } from "@/features/recording/types";

export type SpeakerRole = "prospect" | "rep" | "unknown";

export interface TurnMeta {
  speakerRole: SpeakerRole;
  dominantSpeaker: string | null;
}

export interface TurnDetectorOptions {
  finalTranscript: string;
  interimTranscript: string;
  enabled: boolean;
  endOfUtteranceSeq?: number;
  settleMs?: number;
  minWords?: number;
  finalWords?: TranscriptWord[];
  repLabel?: string;
  /** Skip auto-coach when the turn is attributed to the enrolled rep */
  gateRepTurns?: boolean;
  onTurn: (latestTurn: string, fullFinal: string, meta: TurnMeta) => void;
}

function dominantSpeaker(
  words: TranscriptWord[],
  fromIndex: number
): string | null {
  const counts = new Map<string, number>();
  for (let i = fromIndex; i < words.length; i++) {
    const w = words[i];
    if (!w || w.is_punct || !w.speaker) continue;
    counts.set(w.speaker, (counts.get(w.speaker) || 0) + 1);
  }
  let best: string | null = null;
  let bestN = 0;
  for (const [spk, n] of counts) {
    if (n > bestN) {
      best = spk;
      bestN = n;
    }
  }
  return best;
}

function roleFromSpeaker(speaker: string | null, repLabel: string): SpeakerRole {
  if (!speaker) return "unknown";
  if (speaker === repLabel) return "rep";
  return "prospect";
}

/**
 * Detects end-of-turn from STT finals + optional server EndOfUtterance.
 * Optionally attributes speaker using word-level diarization.
 */
export function useTurnDetector({
  finalTranscript,
  interimTranscript,
  enabled,
  endOfUtteranceSeq = 0,
  settleMs = 800,
  minWords = 6,
  finalWords = [],
  repLabel = "Salesperson",
  gateRepTurns = false,
  onTurn,
}: TurnDetectorOptions): void {
  const lastSeenFinalRef = useRef("");
  const pendingTurnRef = useRef("");
  const wordsAtLastFlushRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const lastEouRef = useRef(0);
  const finalWordsRef = useRef(finalWords);
  finalWordsRef.current = finalWords;
  const onTurnRef = useRef(onTurn);
  onTurnRef.current = onTurn;

  const flushPending = () => {
    const turn = pendingTurnRef.current.trim();
    pendingTurnRef.current = "";
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    const words = turn.split(/\s+/).filter(Boolean).length;
    const from = wordsAtLastFlushRef.current;
    const allWords = finalWordsRef.current;
    wordsAtLastFlushRef.current = allWords.length;

    if (words < minWords) return;

    const dom = dominantSpeaker(allWords, from);
    const speakerRole = roleFromSpeaker(dom, repLabel);
    if (gateRepTurns && speakerRole === "rep") return;

    onTurnRef.current(turn, lastSeenFinalRef.current, {
      speakerRole,
      dominantSpeaker: dom,
    });
  };

  // Recover word cursor after transcript reset
  useEffect(() => {
    if (finalWords.length < wordsAtLastFlushRef.current) {
      wordsAtLastFlushRef.current = finalWords.length;
    }
  }, [finalWords]);

  useEffect(() => {
    if (!enabled) {
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      pendingTurnRef.current = "";
      return;
    }

    const prev = lastSeenFinalRef.current;
    const next = finalTranscript.trim();

    if (next.length < prev.length) {
      lastSeenFinalRef.current = next;
      pendingTurnRef.current = "";
      wordsAtLastFlushRef.current = finalWordsRef.current.length;
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    if (next.length > prev.length) {
      const delta = next.slice(prev.length).trim();
      if (delta) {
        pendingTurnRef.current = pendingTurnRef.current
          ? `${pendingTurnRef.current} ${delta}`.trim()
          : delta;
      }
      lastSeenFinalRef.current = next;
    }
  }, [finalTranscript, enabled]);

  useEffect(() => {
    if (!enabled) {
      lastEouRef.current = endOfUtteranceSeq;
      return;
    }
    if (endOfUtteranceSeq <= lastEouRef.current) return;
    lastEouRef.current = endOfUtteranceSeq;
    flushPending();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endOfUtteranceSeq, enabled, minWords, gateRepTurns, repLabel]);

  useEffect(() => {
    if (!enabled) return;
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    const pending = pendingTurnRef.current.trim();
    const interimEmpty = !interimTranscript.trim();
    if (!pending || !interimEmpty) return;

    timerRef.current = window.setTimeout(() => {
      flushPending();
    }, settleMs);

    return () => {
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finalTranscript, interimTranscript, enabled, settleMs, minWords]);
}
