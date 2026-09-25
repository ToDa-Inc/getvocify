import { VElement, define } from '../v-element.js';
import { followupNeedsRepaint, renderFollowup } from './followup.js';

class VFollowup extends VElement {
  static render(view, element) {
    return renderFollowup(view, element.lang || document.documentElement.lang);
  }

  // A background refetch must never wipe what the rep is typing.
  shouldRepaint(prev, next) {
    return followupNeedsRepaint(prev, next, this.editing);
  }

  /** What the rep will actually send, edits included. */
  get value() {
    return {
      subject: this.querySelector('[data-role="subject"]')?.textContent?.trim() ?? '',
      body: this.querySelector('[data-role="body"]')?.innerText?.trim() ?? '',
    };
  }
}

define('v-followup', VFollowup);
