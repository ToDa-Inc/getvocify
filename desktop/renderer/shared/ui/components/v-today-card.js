import { VElement, define } from "../v-element.js";
import { renderTodayCard } from "../today-card.js";

class VTodayCard extends VElement {
  static render(card, { dismiss, undo, now = Date.now() } = {}) {
    return renderTodayCard(card, { now, dismiss, undo });
  }
}

define("v-today-card", VTodayCard);
