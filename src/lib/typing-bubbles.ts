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

/** The island's turns with a waiting turn for each side that is speaking and has no words on screen (same rule as the dashboard's bubbles). */
export function overlayWithSpeaking<T extends OverlayTurnLike>(turns: T[], speaking: SpeakingSides, prospectLabel: string | null): T[] {
  const { insideLast, extra } = typingPlacement(
    turns.map((turn) => ({ speaker: turn.you ? "rep" : "prospect", pending: turn.pending })),
    speaking,
  );
  if (!insideLast && extra.length === 0) return turns;
  const out = turns.slice();
  if (insideLast) out[out.length - 1] = { ...out[out.length - 1], pending: WAITING_WORDS };
  for (const side of extra) {
    out.push({ key: `speaking-${side}`, you: side === "rep", label: side === "rep" ? null : prospectLabel, text: "", pending: WAITING_WORDS } as T);
  }
  return out;
}
