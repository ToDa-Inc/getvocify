import { VElement, define } from '../v-element.js';
import { renderReviewTabs, reviewTabsNeedRepaint, stepReviewTab } from './review-tabs.js';

class VReviewTabs extends VElement {
  static render(view, element) {
    return renderReviewTabs(view, element.lang || document.documentElement.lang);
  }

  shouldRepaint(prev, next) {
    return reviewTabsNeedRepaint(prev, next);
  }

  get data() {
    return super.data;
  }

  // A repaint replaces the buttons; keyboard focus follows the selected tab.
  set data(next) {
    const hadFocus = this.contains(document.activeElement);
    super.data = next;
    if (hadFocus) this.querySelector('[aria-selected="true"]')?.focus();
  }

  connectedCallback() {
    super.connectedCallback();
    if (this.dataset.vKeys) return;
    this.dataset.vKeys = '1';
    this.addEventListener('keydown', (event) => {
      const view = this.data;
      if (!view?.tabs?.length || !event.target.closest('[role="tab"]')) return;
      const next = stepReviewTab(view.tabs, view.active, event.key);
      if (next === view.active) return;
      event.preventDefault();
      this.dispatchEvent(
        new CustomEvent('v-action', { bubbles: true, detail: { action: 'tab', value: next, element: this } }),
      );
    });
  }
}

define('v-review-tabs', VReviewTabs);
