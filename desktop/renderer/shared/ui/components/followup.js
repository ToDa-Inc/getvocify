import { html } from '../html.js';
import { strings } from '../i18n.js';

/**
 * @typedef {Object} FollowupView   Shape returned by GET /api/v1/memos/{id}/followup
 * @property {'generating'|'ready'|'sent'|'unavailable'} status
 * @property {string} [recipientName]
 * @property {string} [to]
 * @property {string} [phone]
 * @property {string} [subject]
 * @property {string} [body]
 * @property {'email'|'whatsapp'} [channel]
 */

/** Pure: view in, markup out. Node-testable, no DOM. */
export function renderFollowup(view, lang) {
  const t = strings(lang);
  const title = view.recipientName ? t.followupFor(view.recipientName) : t.followupFallback;

  if (view.status === 'generating') {
    return html`<section class="v-paper v-followup" aria-busy="true">
  <p class="v-followup__title">${title}</p>
  <p class="v-followup__pending" role="status">${t.writing}</p>
  <div class="v-followup__skeleton" aria-hidden="true"><span></span><span></span><span></span></div>
</section>`;
  }

  if (view.status === 'sent') {
    return html`<section class="v-paper v-followup is-sent">
  <p class="v-followup__title">${title}</p>
  <p class="v-followup__done" role="status">${view.channel === 'whatsapp' ? t.openedWhatsapp : t.openedMail}</p>
</section>`;
  }

  if (view.status !== 'ready') return html``;

  const primary = view.to ? 'email' : view.phone ? 'whatsapp' : null;
  const pill = (channel) => (primary === channel ? 'v-pill v-pill--primary' : 'v-pill v-pill--ghost');

  return html`<section class="v-paper v-followup">
  <header class="v-followup__head">
    <p class="v-followup__title">${title}</p>
    ${view.to ? html`<span class="v-chip">${view.to}</span>` : ''}
  </header>
  <p class="v-followup__subject" data-role="subject" contenteditable="plaintext-only" spellcheck="true">${view.subject}</p>
  <div class="v-followup__body" data-role="body" contenteditable="plaintext-only" spellcheck="true">${view.body}</div>
  ${view.to ? '' : html`<p class="v-followup__hint">${t.addEmail}</p>`}
  <footer class="v-followup__actions">
    ${view.to ? html`<button type="button" class="${pill('email')}" data-action="send" data-value="email">${t.openMail}</button>` : ''}
    ${view.phone ? html`<button type="button" class="${pill('whatsapp')}" data-action="send" data-value="whatsapp">${t.whatsapp}</button>` : ''}
    <button type="button" class="v-text-action" data-action="copy">${t.copy}</button>
  </footer>
</section>`;
}

/** While the rep is editing, repaint only when the server says something new. */
export function followupNeedsRepaint(prev, next, editing) {
  if (!editing) return true;
  return prev?.status !== next?.status || prev?.subject !== next?.subject || prev?.body !== next?.body;
}
