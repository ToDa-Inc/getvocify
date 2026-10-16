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
