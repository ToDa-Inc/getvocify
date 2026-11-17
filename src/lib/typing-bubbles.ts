import type { RowList } from "./meeting-transcript.ts";

export type SpeakingSides = { rep?: boolean; prospect?: boolean };

type TurnLike = { speaker: string; pending?: string };

/**
 * Where "typing" bubbles go while a side is talking and its words are not on screen yet (a transcription that answers a
 * sentence at a time, so there is no text to show until it is over). A side whose last turn is already showing words that
 * are still settling has its bubble from that turn; any other speaking side gets its own row after the last turn.
 */
export function typingPlacement(turns: TurnLike[], speaking: SpeakingSides): { insideLast: boolean; extra: Array<"prospect" | "rep"> } {
  const last = turns[turns.length - 1];
  const speaker = last?.speaker === "rep" || last?.speaker === "prospect" ? last.speaker : null;
  return {
    insideLast: Boolean(speaker && speaking[speaker] && !last.pending),
    extra: (["prospect", "rep"] as const).filter((side) => speaking[side] && side !== speaker),
  };
}

/** What the island gets as a turn's "words still arriving" when its words are not there yet: it draws the dots for any
 *  pending text, and a no-break space is invisible (and trimmed away if the turn is copied). */
export const WAITING_WORDS = "\u00a0";

type OverlayTurnLike = { key: string; you: boolean; label: string | null; text: string; pending: string };

/** The island's turns with a waiting turn for each side that is speaking and has no words on screen (same rule as the
 * dashboard's bubbles). Only the end of the list changes: the rest is read from `turns` as it is, never copied. */
export function overlayWithSpeaking<T extends OverlayTurnLike>(turns: RowList<T>, speaking: SpeakingSides, prospectLabel: string | null): RowList<T> {
  const last = turns.at(-1);
  const { insideLast, extra } = typingPlacement(last ? [{ speaker: last.you ? "rep" : "prospect", pending: last.pending }] : [], speaking);
  if (!insideLast && extra.length === 0) return turns;
  const n = turns.length;
  const lastShown = insideLast && last ? ({ ...last, pending: WAITING_WORDS } as T) : null;
  const added = extra.map(
    (side) => ({ key: `speaking-${side}`, you: side === "rep", label: side === "rep" ? null : prospectLabel, text: "", pending: WAITING_WORDS }) as T,
  );
  const length = n + added.length;
  const at = (index: number): T | undefined => {
    const i = index < 0 ? length + index : index;
    if (i < 0 || i >= length) return undefined;
    if (i >= n) return added[i - n];
    if (lastShown && i === n - 1) return lastShown;
    return turns.at(i);
  };
  const shared = turns.shared;
  return {
    length,
    at,
    slice: (start = 0, end = length) => {
      const from = Math.max(0, start < 0 ? length + start : Math.min(start, length));
      const to = Math.max(from, end < 0 ? length + end : Math.min(end, length));
      const out: T[] = [];
      for (let i = from; i < to; i++) out.push(at(i) as T);
      return out;
    },
    ...(shared ? { shared: { key: shared.key, length: Math.min(shared.length, lastShown ? n - 1 : n) } } : {}),
  };
}
