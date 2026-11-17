import { meetingLabelIn, sumRows, type MeetingDisplayTurn, type RowList } from "./meeting-transcript.ts";

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

/** Words of each row's proposal line, kept per row and language: a settled row keeps its object. */
const lineWords = { EN: new WeakMap<MeetingDisplayTurn, number>(), ES: new WeakMap<MeetingDisplayTurn, number>() };
/** Their sum over the rows the call's versions share, per language. */
const sumMemo = { EN: new WeakMap<object, number[]>(), ES: new WeakMap<object, number[]>() };

/** How many words the proposal would read (the words of `proposalLines`): a final counts only the rows after the shared ones. */
export function proposalWords(rows: RowList<MeetingDisplayTurn>, language: Language): number {
  const known = lineWords[language];
  const count = (row: MeetingDisplayTurn) => {
    let words = known.get(row);
    if (words === undefined) {
      words = row.text.trim() ? proposalLine(row, language).split(/\s+/).length : 0;
      known.set(row, words);
    }
    return words;
  };
  return sumRows(rows, count, sumMemo[language]);
}
