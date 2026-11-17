import { meetingLabelIn, type MeetingDisplayTurn } from "./meeting-transcript.ts";

type Language = "EN" | "ES";

/** One settled line as the call type proposal reads it: "Label: text", or the text when a line has no label. */
function proposalLine(turn: MeetingDisplayTurn, language: Language): string {
  const label = meetingLabelIn(turn.label, language);
  return label ? `${label}: ${turn.text}` : turn.text;
}

/** The settled lines the call type proposal reads. */
export function proposalLines(rows: MeetingDisplayTurn[], language: Language): string[] {
  return rows.filter((turn) => turn.text.trim()).map((turn) => proposalLine(turn, language));
}

/** Words of each row's proposal line, kept per row: a settled row keeps its object, so a final counts only the rows it changed. */
const lineWords = new WeakMap<MeetingDisplayTurn, { language: Language; words: number }>();

/** How many words the proposal would read (the words of `proposalLines`), without building the lines again on every final. */
export function proposalWords(rows: MeetingDisplayTurn[], language: Language): number {
  let sum = 0;
  for (const row of rows) {
    let known = lineWords.get(row);
    if (known?.language !== language) {
      known = { language, words: row.text.trim() ? proposalLine(row, language).split(/\s+/).length : 0 };
      lineWords.set(row, known);
    }
    sum += known.words;
  }
  return sum;
}
