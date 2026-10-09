import { html } from '../html.js';

export function transcriptView(state) {
  const turns = state?.turns ?? [];
  const interim = state?.interim ?? null;
  if (turns.length === 0 && interim == null) {
    return html`<p class="v-transcript-empty">Escuchando. La transcripción aparecerá aquí.</p>`;
  }
  return html`<div class="v-transcript-log">${turns.map((turn) => html`<p class="v-transcript-turn" data-turn-id="${turn.id}">${turn.text ?? ''}</p>`)}${interim ? html`<p class="v-transcript-turn" data-turn-id="${interim.id}" data-interim="true">${interim.text ?? ''}</p>` : ''}</div>`;
}
