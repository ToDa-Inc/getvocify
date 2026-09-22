import { VElement, define } from "../v-element.js";
import { renderTodayCard } from "../today-card.js";

class VTodayCard extends VElement {
  static render(card) {
    return renderTodayCard(card, { now: Date.now() });
  }
}

define("v-today-card", VTodayCard);
