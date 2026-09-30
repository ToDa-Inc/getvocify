import { VElement, define } from '../v-element.js';
import { followupNeedsRepaint, mailClientOpenLabel, renderFollowup } from './followup.js';

class VFollowup extends VElement {
  /** The rep's pick outlives repaints; the host only remembers it for next time. */
  mailClient = null;

  static render(view, element) {
    const lang = element.lang || document.documentElement.lang;
    return renderFollowup({ ...view, mailClient: element.mailClient ?? view.mailClient }, lang);
  }

  connectedCallback() {
    super.connectedCallback();
    if (this.dataset.vClient) return;
    this.dataset.vClient = '1';
    // Picking Gmail/Outlook updates in place: a repaint would throw away the rep's edits.
    this.addEventListener('click', (event) => {
      const pick = event.target.closest('[data-action="client"]');
      if (!pick || !this.contains(pick)) return;
      this.mailClient = pick.dataset.value;
      this.querySelectorAll('[data-action="client"]').forEach((button) => {
        button.setAttribute('aria-pressed', String(button === pick));
      });
      const send = this.querySelector('[data-role="send-mail"]');
      if (send) {
        send.dataset.value = this.mailClient;
        send.textContent = mailClientOpenLabel(this.mailClient, this.lang || document.documentElement.lang);
      }
    });
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
