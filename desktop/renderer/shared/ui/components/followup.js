import { html, raw } from '../html.js';
import { strings } from '../i18n.js';
import { renderAnimIcon } from './anim-icon.js';

/**
 * @typedef {Object} FollowupView   Shape returned by GET /api/v1/memos/{id}/followup
 * @property {'generating'|'ready'|'sent'|'unavailable'} status
 * @property {string} [recipientName]
 * @property {string} [to]
 * @property {string} [phone]
 * @property {string} [subject]
 * @property {string} [body]
 * @property {'email'|'whatsapp'} [channel]
 * @property {'gmail'|'outlook'|'default'} [mailClient]  host-remembered; the rep's pick
 */

export const MAIL_CLIENTS = ['gmail', 'outlook', 'default'];

// Brand marks, drawn small. The mail app is a plain envelope in the text colour.
const MAIL_ICONS = {
  gmail: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><rect x="2" y="6" width="4" height="13" rx="1" fill="#4285F4"/><rect x="18" y="6" width="4" height="13" rx="1" fill="#34A853"/><path d="M3.5 7.5 12 14l8.5-6.5" fill="none" stroke="#EA4335" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  outlook: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><rect x="12" y="7" width="10" height="11" rx="1.5" fill="#28A8EA"/><rect x="2" y="4" width="13" height="16" rx="2" fill="#0F6CBD"/><ellipse cx="8.5" cy="12" rx="3" ry="3.6" fill="none" stroke="#fff" stroke-width="2"/></svg>',
  default: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="1.75"/><path d="m3.5 7 8.5 6 8.5-6" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/></svg>',
};

export function mailClientOf(value) {
  return MAIL_CLIENTS.includes(value) ? value : 'gmail';
}

export function mailClientName(client, lang) {
  const t = strings(lang);
  return { gmail: 'Gmail', outlook: 'Outlook', default: t.mailApp }[mailClientOf(client)];
}

/** The primary's label: "Abrir en Gmail", or the old "Abrir en el correo" for the mail app. */
export function mailClientOpenLabel(client, lang) {
  const t = strings(lang);
  return mailClientOf(client) === 'default' ? t.openMail : t.openIn(mailClientName(client, lang));
}

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

  // The draft opens in the rep's mail even without an address: they type the "To" there.
  const client = mailClientOf(view.mailClient);
  const clients = MAIL_CLIENTS.map(
    (id) => html`<button type="button" class="v-mail-client" data-action="client" data-value="${id}" aria-pressed="${id === client ? 'true' : 'false'}" aria-label="${mailClientName(id, lang)}" title="${mailClientName(id, lang)}">${raw(MAIL_ICONS[id])}</button>`,
  );

  return html`<section class="v-paper v-followup">
  <header class="v-followup__head">
    <p class="v-followup__title">${title}</p>
    ${view.to ? html`<span class="v-chip">${view.to}</span>` : ''}
  </header>
  <p class="v-followup__subject" data-role="subject" contenteditable="plaintext-only" spellcheck="true">${view.subject}</p>
  <div class="v-followup__body" data-role="body" contenteditable="plaintext-only" spellcheck="true">${view.body}</div>
  <footer class="v-followup__actions">
    <div class="v-mail-clients" role="group" aria-label="${t.openWith}">${clients}</div>
    <button type="button" class="v-pill v-pill--primary" data-role="send-mail" data-action="send" data-value="${client}">${mailClientOpenLabel(client, lang)}</button>
    ${view.phone ? html`<button type="button" class="v-pill v-pill--ghost" data-action="send" data-value="whatsapp">${t.whatsapp}</button>` : ''}
    <button type="button" class="v-text-action v-text-action--icon" data-action="copy">${renderAnimIcon('copy', { size: 14, stroke: 1.75 })}<span data-v-label>${t.copy}</span></button>
  </footer>
</section>`;
}

/** While the rep is editing, repaint only when the server says something new. */
export function followupNeedsRepaint(prev, next, editing) {
  if (!editing) return true;
  return prev?.status !== next?.status || prev?.subject !== next?.subject || prev?.body !== next?.body;
}
