import test from 'node:test';
import assert from 'node:assert/strict';
import { html, raw, renderToString, escapeHtml } from './html.js';
import { composeTarget } from './compose.js';

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
