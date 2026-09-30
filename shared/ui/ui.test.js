import test from 'node:test';
import assert from 'node:assert/strict';
import { html, raw, renderToString, escapeHtml } from './html.js';
import { composeTarget } from './compose.js';
import { followupNeedsRepaint, renderFollowup } from './components/followup.js';

test('html escapes every interpolation', () => {
  const out = renderToString(html`<p title="${'"x"'}">${'<script>alert(1)</script>'}</p>`);
  assert.equal(out, '<p title="&quot;x&quot;">&lt;script&gt;alert(1)&lt;/script&gt;</p>');
});

test('nested fragments are not double-escaped; arrays join; false/null render nothing', () => {
  const items = ['a&b', 'c'].map((x) => html`<li>${x}</li>`);
  const out = renderToString(html`<ul>${items}${false}${null}${raw('<hr>')}</ul>`);
  assert.equal(out, '<ul><li>a&amp;b</li><li>c</li><hr></ul>');
});

test('escapeHtml handles null and numbers', () => {
  assert.equal(escapeHtml(null), '');
  assert.equal(escapeHtml(42), '42');
});

test('mailto encodes subject and body', () => {
  const r = composeTarget({ channel: 'email', to: 'marina@tenes.io', subject: 'Hola & más', body: 'a b\nc' });
  assert.deepEqual(r, { ok: true, url: 'mailto:marina@tenes.io?subject=Hola%20%26%20m%C3%A1s&body=a%20b%0Ac' });
});

test('long mailto falls back to subject-only draft', () => {
  const r = composeTarget({ channel: 'email', to: 'a@b.co', subject: 'S', body: 'x'.repeat(3000) });
  assert.equal(r.ok, false);
  assert.equal(r.reason, 'too_long');
  assert.equal(r.fallback, 'mailto:a@b.co?subject=S');
});

test('gmail and outlook compose URLs', () => {
  assert.match(composeTarget({ channel: 'email', to: 'a@b.co', subject: 'S', body: 'B', mailClient: 'gmail' }).url,
    /^https:\/\/mail\.google\.com\/mail\/\?view=cm&fs=1&to=a%40b\.co&su=S&body=B$/);
  assert.match(composeTarget({ channel: 'email', to: 'a@b.co', subject: 'S', body: 'B', mailClient: 'outlook' }).url,
    /^https:\/\/outlook\.office\.com\/mail\/deeplink\/compose\?to=a%40b\.co&subject=S&body=B$/);
});

test('whatsapp strips formatting; rejects missing numbers and bad emails', () => {
  assert.equal(composeTarget({ channel: 'whatsapp', phone: '+34 600 111 222', body: 'Hola' }).url, 'https://wa.me/34600111222?text=Hola');
  assert.deepEqual(composeTarget({ channel: 'whatsapp', phone: '' }), { ok: false, reason: 'no_phone' });
  assert.deepEqual(composeTarget({ channel: 'email', to: 'not-an-email' }), { ok: false, reason: 'no_email' });
});

test('no address still opens a draft in every mail client', () => {
  assert.equal(composeTarget({ channel: 'email', to: '', subject: 'S', body: 'B', mailClient: 'gmail' }).url,
    'https://mail.google.com/mail/?view=cm&fs=1&su=S&body=B');
  assert.equal(composeTarget({ channel: 'email', subject: 'S', mailClient: 'outlook' }).url,
    'https://outlook.office.com/mail/deeplink/compose?subject=S');
  assert.equal(composeTarget({ channel: 'email', subject: 'S' }).url, 'mailto:?subject=S');
});

const ready = {
  status: 'ready',
  recipientName: 'Marina',
  to: 'marina@tenes.io',
  phone: '+34600111222',
  subject: 'Caso de logística',
  body: 'Hola Marina,\ngracias por el rato de hoy.',
};

test('generating state is busy, announces itself, and reserves space', () => {
  const out = renderToString(renderFollowup({ status: 'generating', recipientName: 'Marina' }, 'es'));
  assert.match(out, /aria-busy="true"/);
  assert.match(out, /role="status">Escribiendo el seguimiento…/);
  assert.match(out, /v-followup__skeleton/);
});

test('ready state: the picked mail client is primary, WhatsApp is ghost, copy always present', () => {
  const out = renderToString(renderFollowup(ready, 'es'));
  assert.match(out, /class="v-pill v-pill--primary" data-role="send-mail" data-action="send" data-value="gmail">Abrir en Gmail</);
  assert.match(out, /data-action="client" data-value="gmail" aria-pressed="true" aria-label="Gmail"/);
  assert.match(out, /data-action="client" data-value="outlook" aria-pressed="false" aria-label="Outlook"/);
  assert.match(out, /data-action="client" data-value="default" aria-pressed="false" aria-label="App de correo"/);
  assert.doesNotMatch(out, />Enviar</);
  assert.match(out, /class="v-pill v-pill--ghost" data-action="send" data-value="whatsapp">WhatsApp</);
  assert.match(out, /data-action="copy"><span class="v-ai v-ai--copy"[^>]*>.*?<\/span><span data-v-label>Copiar</);
  const outlook = renderToString(renderFollowup({ ...ready, mailClient: 'outlook' }, 'en'));
  assert.match(outlook, /data-value="outlook">Open in Outlook</);
  const app = renderToString(renderFollowup({ ...ready, mailClient: 'default' }, 'es'));
  assert.match(app, /data-value="default">Abrir en el correo</);
  assert.match(renderToString(renderFollowup({ ...ready, mailClient: 'nonsense' }, 'es')), /data-value="gmail">Abrir en Gmail</);
});

test('no email: no nagging hint, the draft still opens (the rep types the address)', () => {
  const out = renderToString(renderFollowup({ ...ready, to: '' }, 'es'));
  assert.doesNotMatch(out, /v-followup__hint/);
  assert.doesNotMatch(out, /Sin email/);
  assert.match(out, /v-pill--primary" data-role="send-mail" data-action="send" data-value="gmail"/);
  assert.match(out, /v-pill--ghost" data-action="send" data-value="whatsapp"/);
});

test('draft text from a transcript cannot inject markup', () => {
  const out = renderToString(renderFollowup({ ...ready, body: '<img src=x onerror=alert(1)>' }, 'es'));
  assert.doesNotMatch(out, /<img/);
  assert.match(out, /&lt;img src=x onerror=alert\(1\)&gt;/);
});

test('sent state says what we know: it was opened, not that it was delivered', () => {
  const mail = renderToString(renderFollowup({ status: 'sent', channel: 'email', recipientName: 'Marina' }, 'es'));
  assert.match(mail, /is-sent/);
  assert.match(mail, /role="status">Abierto en el correo/);
  assert.doesNotMatch(mail, /enviado/i);
  assert.doesNotMatch(mail, /delivered/i);
  const wa = renderToString(renderFollowup({ status: 'sent', channel: 'whatsapp' }, 'es'));
  assert.match(wa, /Abierto en WhatsApp\./);
  assert.doesNotMatch(wa, /enviado/i);
  assert.doesNotMatch(wa, /delivered/i);
  assert.doesNotMatch(mail, />Enviar</);
  assert.doesNotMatch(mail, /data-value="email">Enviar</);
});

test('unavailable renders nothing; English labels switch with lang', () => {
  assert.equal(renderToString(renderFollowup({ status: 'unavailable' }, 'es')), '');
  assert.match(renderToString(renderFollowup(ready, 'en-GB')), /Follow-up for Marina/);
});

test('a refetch of the same draft keeps the edits; a new status or another draft repaints', () => {
  assert.equal(followupNeedsRepaint(ready, { ...ready }, false), true);
  assert.equal(followupNeedsRepaint(ready, { ...ready }, true), false);
  assert.equal(followupNeedsRepaint(ready, { status: 'sent', channel: 'email' }, true), true);
  assert.equal(followupNeedsRepaint(ready, { ...ready, body: 'Hola Pedro,' }, true), true);
});
