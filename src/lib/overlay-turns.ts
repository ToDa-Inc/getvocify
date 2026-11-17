import { meetingLabelIn, overlayTurnOf, type MeetingDisplayTurn, type MeetingOverlayTurn } from "./meeting-transcript.ts";
import { overlayWithSpeaking, type SpeakingSides } from "./typing-bubbles.ts";

/**
 * Maps rows to the values built from them, once per row. A row that is the same object as on the last call (or has the
 * same fields: a row is rebuilt when a final lands, with the same words) keeps its value, so an update builds only the
 * rows that changed. The value is the same object each time, which is what lets React and `firstChanged` skip it.
 */
export class RowMemo<T extends object, R> {
  private rows: T[] = [];
  private out: R[] = [];
  private ctx: string | null = null;
  /** Values built since the start: what an update costs in new objects. */
  built = 0;

  update(rows: T[], ctx: string, make: (row: T) => R): R[] {
    // The same rows again (the island's clock while nothing new was said): the same values, without walking them.
    if (rows === this.rows && ctx === this.ctx) return this.out;
    if (ctx !== this.ctx) {
      this.ctx = ctx;
      this.rows = [];
      this.out = [];
    }
    const out: R[] = new Array(rows.length);
    for (let i = 0; i < rows.length; i++) {
      if (i < this.rows.length && (rows[i] === this.rows[i] || sameFields(rows[i], this.rows[i]))) {
        out[i] = this.out[i];
      } else {
        out[i] = make(rows[i]);
        this.built += 1;
      }
    }
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
export function firstChanged<T>(prev: T[] | null, next: T[]): number {
  if (!prev) return 0;
  if (prev === next) return next.length;
  const shared = Math.min(prev.length, next.length);
  let index = 0;
  while (index < shared && prev[index] === next[index]) index += 1;
  return index;
}

export type OverlayContext = { prospect: string | null; language: "EN" | "ES" };

/**
 * What the island holds of the overlay, and what it needs next. Each call returns the turns from the first one that
 * changed on, or null when nothing it shows changed. The island keeps the turns before that index.
 */
export class OverlayFeed {
  private readonly rows = new RowMemo<MeetingDisplayTurn, MeetingOverlayTurn>();
  private sent: MeetingOverlayTurn[] | null = null;
  private head = "";

  next(rows: MeetingDisplayTurn[], { prospect, language }: OverlayContext, manyVoices: boolean, speaking: SpeakingSides, head: string): { from: number; turns: MeetingOverlayTurn[] } | null {
    const ctx = { prospect, manyVoices };
    const base = this.rows.update(rows, `${prospect ?? ""}|${manyVoices}|${language}`, (row) => {
      const turn = overlayTurnOf(row, ctx);
      return { ...turn, label: meetingLabelIn(turn.label, language) };
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

