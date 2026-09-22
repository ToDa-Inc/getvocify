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

export function renderTodayCard(card, { now }) {
  const undoOpen = card.undoDeadline != null && Date.parse(card.undoDeadline) >= now;
  return html`<article class="v-today-card" data-id="${card.id}" tabindex="-1">
  <p>${card.reason}</p>
  ${card.status === "pending" ? html`<button type="button" data-action="dismiss">Descartar</button>` : ""}
  ${undoOpen ? html`<button type="button" data-action="undo">Deshacer</button>` : ""}
</article>`;
}
