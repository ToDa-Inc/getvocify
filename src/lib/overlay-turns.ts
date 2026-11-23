import { meetingLabelIn, overlayTurnOf, sharedRows, type MeetingDisplayTurn, type MeetingOverlayTurn, type RowList } from "./meeting-transcript.ts";
import { overlayWithSpeaking, type SpeakingSides } from "./typing-bubbles.ts";
import { NO_TEAM, type TeamSide } from "./meeting-team.ts";

/**
 * Maps rows to the values built from them, once per row. A row that is the same object as before (or has the same fields
 * as the row the last list had in its place: a row is rebuilt when a final lands, with the same words) keeps its value,
 * so an update builds only the rows that changed, and the value is the same object each time, which is what lets React
 * and `firstChanged` skip it. The result is a view: a row is mapped when it is read (the screen reads its window, the
 * island what changed), and the rows a list shares with the lists before it stay shared.
 */
export class RowMemo<T extends object, R> {
  private rows: RowList<T> | null = null;
  private out: RowList<R> | null = null;
  private ctx: string | null = null;
  private values = new WeakMap<T, R>();
  /** One key per key of the rows: mapped lists of rows that share are shared the same way. */
  private keys = new WeakMap<object, object>();
  /** Values built since the start: what an update costs in new objects. */
  built = 0;

  update(rows: RowList<T>, ctx: string, make: (row: T) => R): RowList<R> {
    // The same rows again (the island's clock while nothing new was said): the same values.
    if (rows === this.rows && ctx === this.ctx && this.out) return this.out;
    if (ctx !== this.ctx) {
      this.ctx = ctx;
      this.rows = null;
      this.values = new WeakMap();
      this.keys = new WeakMap();
    }
    const before = this.rows;
    const values = this.values;
    const valueOf = (row: T, index: number): R => {
      let value = values.get(row);
      if (value === undefined) {
        const was = before && index < before.length ? before.at(index) : undefined;
        const kept = was !== undefined && sameFields(row, was) ? values.get(was) : undefined;
        value = kept ?? make(row);
        if (kept === undefined) this.built += 1;
        values.set(row, value);
      }
      return value;
    };
    const shared = rows.shared;
    let key: object | undefined;
    if (shared) {
      key = this.keys.get(shared.key);
      if (!key) this.keys.set(shared.key, (key = {}));
    }
    const out: RowList<R> = {
      length: rows.length,
      at: (index) => {
        const i = index < 0 ? rows.length + index : index;
        const row = rows.at(i);
        return row === undefined ? undefined : valueOf(row, i);
      },
      slice: (start = 0, end = rows.length) => {
        const from = Math.max(0, start < 0 ? rows.length + start : Math.min(start, rows.length));
        const to = Math.max(from, end < 0 ? rows.length + end : Math.min(end, rows.length));
        const list: R[] = new Array(to - from);
        for (let i = from; i < to; i++) list[i - from] = valueOf(rows.at(i) as T, i);
        return list;
      },
      ...(shared && key ? { shared: { key, length: shared.length } } : {}),
    };
    this.rows = rows;
    this.out = out;
    return out;
  }
}

/** Two plain records with the same fields (arrays compared item by item). */
function sameFields(a: object, b: object | undefined): boolean {
  if (!b) return false;
  const left = a as Record<string, unknown>;
  const right = b as Record<string, unknown>;
  const keys = Object.keys(left);
  if (keys.length !== Object.keys(right).length) return false;
  return keys.every((key) => {
    const x = left[key];
    const y = right[key];
    if (Array.isArray(x) && Array.isArray(y)) return x.length === y.length && x.every((item, index) => item === y[index]);
    return x === y;
  });
}

/** The index of the first item that is not the same object in `prev` (null: nothing sent yet, so from the start). */
export function firstChanged<T>(prev: RowList<T> | null, next: RowList<T>): number {
  if (!prev) return 0;
  return sharedRows(prev, next);
}

export type OverlayContext = { prospect: string | null; language: "EN" | "ES"; /** The rep's colleagues: their lines are marked as the rep's side. */ team?: TeamSide };

/**
 * A line heard with the other side but said by one of the rep's colleagues: the rep's side from then on, for the live help
 * and the screens, keeping its name and voice (the voice can still be named as someone else). Every other row as it is.
 */
export function withTeam(row: MeetingDisplayTurn, team: TeamSide): MeetingDisplayTurn {
  return row.speaker === "prospect" && team.has(row.name) ? { ...row, speaker: "rep", team: true } : row;
}

/**
 * What the island holds of the overlay, and what it needs next. Each call returns the turns from the first one that
 * changed on, or null when nothing it shows changed. The island keeps the turns before that index.
 */
export class OverlayFeed {
  private readonly rows = new RowMemo<MeetingDisplayTurn, MeetingOverlayTurn>();
  private sent: RowList<MeetingOverlayTurn> | null = null;
  private head = "";

  next(rows: RowList<MeetingDisplayTurn>, { prospect, language, team = NO_TEAM }: OverlayContext, manyVoices: boolean, speaking: SpeakingSides, head: string): { from: number; turns: RowList<MeetingOverlayTurn> } | null {
    const ctx = { prospect, manyVoices };
    const base = this.rows.update(rows, `${prospect ?? ""}|${manyVoices}|${language}|${team.key}`, (row) => {
      // A colleague's line keeps you:false, so an island that does not know `team` still shows it, named, as before.
      const turn = overlayTurnOf(row, ctx);
      const ours = row.speaker === "prospect" && team.has(row.name);
      return { ...turn, label: meetingLabelIn(turn.label, language), ...(ours ? { team: true } : {}) };
    });
    const turns = overlayWithSpeaking(base, speaking, prospect?.trim() || null);
    const from = firstChanged(this.sent, turns);
    if (this.sent && from === turns.length && from === this.sent.length && head === this.head) return null;
    this.sent = turns;
    this.head = head;
    return { from, turns };
  }

  /** The island was given a whole overlay outside this feed (a recording starts with none): what it holds is that. */
  reset(): void {
    this.sent = [];
    this.head = "";
  }
}

