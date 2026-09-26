// One Hoy card. The server version and undo deadline win. Motion never extends that deadline.
import { html } from "./html.js";

export const TODAY_EMPTY_FOCUS = "today-empty";

export function reduceTodayList(state, event) {
  const cards = dedupe(state.cards);
  if (event.type === "action_result") {
    return {
      cards: cards.map((card) => card.id === event.id
        ? { ...card, status: event.status, version: event.version, undoDeadline: event.undoDeadline }
        : card),
      focusId: event.id,
    };
  }
  if (event.type === "undo") {
    return {
      cards: cards.map((card) => card.id === event.id
        ? { ...card, status: "pending", version: event.version, undoDeadline: null }
        : card),
      focusId: event.id,
    };
  }
  if (event.type === "conflict") {
    return {
      cards: cards.map((card) => card.id === event.card.id ? { ...card, ...event.card, id: card.id } : card),
      focusId: event.card.id,
    };
  }
  if (event.type === "remove") {
    const next = cards.filter((card) => card.id !== event.id);
    return { cards: next, focusId: next.length ? next[0].id : TODAY_EMPTY_FOCUS };
  }
  return { cards, focusId: state.focusId ?? null };
}

export function exitMotion(reducedMotion) {
  if (reducedMotion) return { opacity: true, transform: false, height: false };
  return { opacity: true, transform: true, height: true, measureHeight: true };
}

export function presentExit(card, reducedMotion) {
  return { ...card, motion: exitMotion(reducedMotion) };
}

/** Rows that left keep their place, marked leaving, until dropLeaving: nothing jumps while they fade. */
export function retainLeaving(previous, next, keyOf) {
  const out = next.map((entry) => ({ entry, leaving: false }));
  const present = new Set(next.map(keyOf));
  let cursor = 0;
  for (const row of previous) {
    const key = keyOf(row.entry);
    if (present.has(key)) {
      cursor = out.findIndex((candidate) => !candidate.leaving && keyOf(candidate.entry) === key) + 1;
    } else {
      out.splice(cursor, 0, { entry: row.entry, leaving: true });
      cursor += 1;
    }
  }
  return out;
}

export function dropLeaving(rows, key, keyOf) {
  return rows.filter((row) => !(row.leaving && keyOf(row.entry) === key));
}

function dedupe(cards) {
  const seen = new Set();
  const out = [];
  for (const card of cards) {
    if (seen.has(card.id)) continue;
    seen.add(card.id);
    out.push(card);
  }
  return out;
}

export function renderTodayCard(card, { now, dismiss, undo }) {
  const undoOpen = card.undoDeadline != null && Date.parse(card.undoDeadline) >= now;
  return html`<article class="v-today-card" data-id="${card.id}" tabindex="-1">
  <p>${card.reason}</p>
  ${card.status === "pending" ? html`<button type="button" data-action="dismiss">${dismiss}</button>` : ""}
  ${undoOpen ? html`<button type="button" data-action="undo">${undo}</button>` : ""}
</article>`;
}
