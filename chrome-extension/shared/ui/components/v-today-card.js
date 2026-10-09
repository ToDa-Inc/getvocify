import { VElement, define } from "../v-element.js";
import { renderTodayCard } from "../today-card.js";

export class VTodayCard extends VElement {
  static render(card, { dismiss, undo, confirm, review, now = Date.now() } = {}) {
    return renderTodayCard(card, { now, dismiss, undo, confirm, review });
  }
}

define("v-today-card", VTodayCard);
