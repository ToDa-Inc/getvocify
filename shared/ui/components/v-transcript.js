import { reconcileTranscript } from '../transcript.js';
import { renderToString } from '../html.js';
import { transcriptView } from './transcript.js';

// Keeps confirmed turn nodes. A newer revision replaces only the changed span.
export class VTranscript extends HTMLElement {
  #view = { revision: 0, turns: [], interim: null };

  connectedCallback() {
    if (!this.querySelector('.v-transcript-log, .v-transcript-empty')) this.#paintFull();
  }

  get data() {
    return this.#view;
  }

  set data(next) {
    const resolved = reconcileTranscript(this.#view, next) ?? this.#view;
    const same = resolved === this.#view;
    this.#view = resolved;
    if (!this.isConnected || same) return;
    this.#paintPatched();
  }

  #paintFull() {
    this.innerHTML = renderToString(transcriptView(this.#view));
  }

  #paintPatched() {
    const log = this.querySelector('.v-transcript-log');
    if (!log) {
      this.#paintFull();
      return;
    }
    const turns = this.#view.turns ?? [];
    const ids = new Set(turns.map((turn) => turn.id));
    for (const node of [...log.querySelectorAll('.v-transcript-turn')]) {
      const id = node.dataset.turnId;
      if (node.dataset.interim === 'true') node.remove();
      else if (!ids.has(id)) node.remove();
    }
    for (const turn of turns) {
      let node = log.querySelector(`[data-turn-id="${CSS.escape(turn.id)}"]`);
      if (!node) {
        node = document.createElement('p');
        node.className = 'v-transcript-turn';
        node.dataset.turnId = turn.id;
        log.append(node);
      }
      node.removeAttribute('data-interim');
      if (node.textContent !== (turn.text ?? '')) node.textContent = turn.text ?? '';
    }
    const interim = this.#view.interim;
    if (interim) {
      const node = document.createElement('p');
      node.className = 'v-transcript-turn';
      node.dataset.turnId = interim.id;
      node.dataset.interim = 'true';
      node.textContent = interim.text ?? '';
      log.append(node);
    }
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('v-transcript')) {
  customElements.define('v-transcript', VTranscript);
}
