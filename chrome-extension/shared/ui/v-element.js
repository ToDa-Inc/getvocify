import { renderToString } from './html.js';

// Light-DOM custom element: data in through `.data`, intent out through one
// bubbling `v-action` event. Components never fetch and never navigate; the
// host surface (extension, desktop, web) owns effects.
export class VElement extends HTMLElement {
  #data = null;
  editing = false;

  connectedCallback() {
    if (!this.dataset.vBound) {
      this.dataset.vBound = '1';
      this.addEventListener('click', (event) => this.#onClick(event));
      this.addEventListener('input', () => {
        this.editing = true;
      });
    }
    this.#paint();
  }

  get data() {
    return this.#data;
  }

  set data(next) {
    const prev = this.#data;
    this.#data = next;
    if (this.isConnected && this.shouldRepaint(prev, next)) this.#paint();
  }

  // Override to protect in-progress edits from background refetches.
  shouldRepaint() {
    return true;
  }

  #paint() {
    this.innerHTML = this.#data == null ? '' : renderToString(this.constructor.render(this.#data, this));
  }

  #onClick(event) {
    const target = event.target.closest('[data-action]');
    if (!target || !this.contains(target)) return;
    this.dispatchEvent(
      new CustomEvent('v-action', {
        bubbles: true,
        detail: { action: target.dataset.action, value: target.dataset.value ?? null, element: this },
      }),
    );
  }

  static render() {
    return '';
  }
}

export function define(tag, ElementClass) {
  if (!customElements.get(tag)) customElements.define(tag, ElementClass);
}
