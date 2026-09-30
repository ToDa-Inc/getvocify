// End-to-end check for live call awareness (HubSpot dialers → extension → backend → stream).
//
// A real HubSpot Calling Extensions SDK dialer runs in an iframe of a fake HubSpot page
// (served by Playwright routes; the page hosts it with the SDK's own IFrameManager, as
// HubSpot does). The unpacked Vocify extension catches the call messages and reports
// them; the script asserts what the backend's /live-calls/current and /live-calls/stream
// say. Covers: dialer on a record page, dialer nested in a HubSpot frame, legacy SDK
// payloads (no externalCallId) and HubSpot's separate calling window.
//
// Setup (once):
//   npm i -g playwright  (or point PLAYWRIGHT at any playwright/index.mjs) && npx playwright install chromium
//   (cd /tmp && npm pack @hubspot/calling-extensions-sdk && tar xzf hubspot-calling-extensions-sdk-*.tgz)
// Run (backend from this checkout on API, signed-in test user):
//   PLAYWRIGHT=/path/to/playwright/index.mjs HUBSPOT_SDK_ESM=/tmp/package/dist/main.esm.js \
//   VOCIFY_API=http://localhost:8888/api/v1 VOCIFY_E2E_EMAIL=… VOCIFY_E2E_PASSWORD=… \
//   node scripts/e2e-live-call-hubspot.mjs
import { readFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const env = (name, fallback) => {
  const value = process.env[name] || fallback;
  if (!value) throw new Error(`Set ${name}`);
  return value;
};
const { chromium } = await import(env('PLAYWRIGHT', 'playwright'));
const EXT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../chrome-extension');
const SDK = readFileSync(env('HUBSPOT_SDK_ESM'), 'utf8');
const API = env('VOCIFY_API', 'http://localhost:8888/api/v1');
const HS = 'https://app.hubspot.com';
const DIALER = 'https://dialer.vocify-e2e.test';

const creds = { email: env('VOCIFY_E2E_EMAIL'), password: env('VOCIFY_E2E_PASSWORD') };
const login = await fetch(`${API}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: creds.email, password: creds.password }),
});
if (!login.ok) throw new Error(`login failed ${login.status}`);
const loginBody = await login.json();
const accessToken = loginBody.access_token || loginBody.accessToken || loginBody.session?.access_token;
const refreshToken = loginBody.refresh_token || loginBody.refreshToken || loginBody.session?.refresh_token;
if (!accessToken) throw new Error(`no access token in login response keys=${Object.keys(loginBody)}`);
const auth = { Authorization: `Bearer ${accessToken}` };

// Follow the stream the desktop app will use.
const streamEvents = [];
const streamAbort = new AbortController();
(async () => {
  const res = await fetch(`${API}/live-calls/stream`, { headers: auth, signal: streamAbort.signal });
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      if (chunk.startsWith('data: ')) streamEvents.push(JSON.parse(chunk.slice(6)));
    }
  }
})().catch((e) => { if (e.name !== 'AbortError') console.error('stream error', e); });

const hostPage = (dialerSrc) => `<!doctype html><html><body>
<h1>Fake HubSpot record</h1><div id="calling"></div>
<script type="module">
  import { IFrameManager } from '${HS}/__sdk.js';
  window.hostSaw = [];
  new IFrameManager({
    iFrameOptions: { src: ${JSON.stringify(dialerSrc)}, hostElementSelector: '#calling', width: '300px', height: '400px' },
    onMessageHandler: (m) => window.hostSaw.push(m.type),
  });
</script></body></html>`;

const nestedRecordPage = (remoteSrc) => `<!doctype html><html><body>
<h1>Fake HubSpot record (calling remote in a HubSpot frame)</h1>
<iframe src=${JSON.stringify(remoteSrc)} width="320" height="420"></iframe></body></html>`;

const dialerPage = `<!doctype html><html><body><p>fake dialer</p>
<script type="module">
  import CallingExtensions from '${DIALER}/__sdk.js';
  const params = new URL(location.href).searchParams;
  const id = params.get('call');
  const legacy = params.get('legacy') === '1';
  const ext = new CallingExtensions({
    debugMode: false,
    eventHandlers: {
      onReady: () => {
        ext.initialized({ isLoggedIn: true });
        const start = legacy
          ? { phoneNumber: '+34600111222', createEngagement: true }
          : { externalCallId: id, toNumber: '+34600111222', fromNumber: '+34910000000', callStartTime: Date.now(), createEngagement: true };
        setTimeout(() => ext.outgoingCall(start), 200);
        setTimeout(() => ext.callAnswered(legacy ? {} : { externalCallId: id }), 700);
        setTimeout(() => ext.callEnded({ ...(legacy ? {} : { externalCallId: id }), engagementId: 4411, callEndStatus: 'COMPLETED' }), 1200);
        setTimeout(() => ext.callCompleted({ ...(legacy ? {} : { externalCallId: id }), engagementId: 4411 }), 1700);
      },
    },
  });
</script></body></html>`;

const html = (body) => ({ status: 200, contentType: 'text/html', body });
const js = { status: 200, contentType: 'text/javascript', headers: { 'Access-Control-Allow-Origin': '*' }, body: SDK };

const userDataDir = mkdtempSync(path.join(tmpdir(), 'vocify-e2e-'));
const context = await chromium.launchPersistentContext(userDataDir, {
  channel: 'chromium',
  headless: true,
  args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
});

await context.route(`${HS}/**`, (route) => {
  const url = new URL(route.request().url());
  if (url.pathname === '/__sdk.js') return route.fulfill(js);
  if (url.pathname.startsWith('/calling-remote')) {
    return route.fulfill(html(hostPage(`${DIALER}/?call=${url.searchParams.get('call')}`)));
  }
  if (url.pathname.startsWith('/calling-window')) {
    return route.fulfill(html(hostPage(`${DIALER}/?call=${url.searchParams.get('call')}`)));
  }
  const scenario = url.searchParams.get('scenario');
  if (scenario === 'nested') {
    return route.fulfill(html(nestedRecordPage(`${HS}/calling-remote?call=${url.searchParams.get('call')}`)));
  }
  if (scenario === 'none') return route.fulfill(html('<h1>record without dialer</h1>'));
  const legacy = scenario === 'legacy' ? '&legacy=1' : '';
  return route.fulfill(html(hostPage(`${DIALER}/?call=${url.searchParams.get('call')}${legacy}`)));
});
await context.route(`${DIALER}/**`, (route) => {
  const url = new URL(route.request().url());
  if (url.pathname === '/__sdk.js') return route.fulfill(js);
  return route.fulfill(html(dialerPage));
});

let sw = context.serviceWorkers()[0];
if (!sw) sw = await context.waitForEvent('serviceworker');
await sw.evaluate(
  async ({ api, accessToken, refreshToken }) => {
    await chrome.storage.local.set({ api_base: api, accessToken, refreshToken });
  },
  { api: API, accessToken, refreshToken },
);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const current = async () => (await (await fetch(`${API}/live-calls/current`, { headers: auth })).json()).call;
async function settle(pred, ms = 10000) {
  const until = Date.now() + ms;
  let call = await current();
  while (!pred(call) && Date.now() < until) {
    await sleep(250);
    call = await current();
  }
  return call;
}
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  — ${detail}` : ''}`);
}

// 1. Dialer embedded directly in a contact record page.
const page = await context.newPage();
const callDirect = `e2e-direct-${Date.now()}`;
await page.goto(`${HS}/contacts/1234/record/0-1/901?call=${callDirect}`);
let call = await settle((c) => c?.external_call_id === callDirect && c.status === 'completed');
check('direct: host page received SDK messages (handshake works)',
  (await page.evaluate(() => window.hostSaw)).includes('OUTGOING_CALL_STARTED'),
  JSON.stringify(await page.evaluate(() => window.hostSaw)));
check('direct: backend has the call on contact 901', call?.contact_id === '901' && call?.contact_source === 'page', JSON.stringify(call && { id: call.external_call_id, contact: call.contact_id, src: call.contact_source }));
check('direct: lifecycle completed with engagement', call?.status === 'completed' && call?.engagement_id === '4411' && call?.end_status === 'COMPLETED' && !!call?.answered_at, `${call?.status} eng=${call?.engagement_id} end=${call?.end_status}`);
check('direct: remote number captured', call?.remote_number === '+34600111222', call?.remote_number);

// 2. Dialer nested inside a HubSpot calling-remote frame.
const callNested = `e2e-nested-${Date.now()}`;
await page.goto(`${HS}/contacts/1234/record/0-1/902?scenario=nested&call=${callNested}`);
call = await settle((c) => c?.external_call_id === callNested && c.status === 'completed');
check('nested: caught from inner HubSpot frame, contact from top tab URL', call?.external_call_id === callNested && call?.contact_id === '902' && call?.status === 'completed', JSON.stringify(call && { id: call.external_call_id, contact: call.contact_id, status: call.status }));

// 3. Legacy SDK payload (no externalCallId, phoneNumber instead of toNumber).
await page.goto(`${HS}/contacts/1234/record/0-1/904?scenario=legacy&call=x`);
call = await settle((c) => c?.external_call_id?.startsWith('synthetic-') && c.status === 'completed');
check('legacy: synthetic id groups the lifecycle', call?.external_call_id?.startsWith('synthetic-') && call?.contact_id === '904' && call?.status === 'completed' && call?.remote_number === '+34600111222', JSON.stringify(call && { id: call.external_call_id, contact: call.contact_id, status: call.status, n: call.remote_number }));

// 4. Calling window: dialer in a separate HubSpot tab that is not a record page.
await page.goto(`${HS}/contacts/1234/record/0-1/903?scenario=none`);
await page.bringToFront();
await sleep(1500);
const callWin = `e2e-window-${Date.now()}`;
const win = await context.newPage();
await win.goto(`${HS}/calling-window/1234?call=${callWin}`);
call = await settle((c) => c?.external_call_id === callWin && c.status === 'completed');
check('calling window: uses the record tab the rep was on', call?.external_call_id === callWin && call?.contact_id === '903', JSON.stringify(call && { id: call.external_call_id, contact: call.contact_id, src: call.contact_source }));

await sleep(500);
const types = streamEvents.map((e) => `${e.type}:${e.call?.external_call_id ?? '-'}:${e.call?.status ?? '-'}`);
check('stream: snapshot first, then call updates', streamEvents[0]?.type === 'snapshot' && streamEvents.filter((e) => e.type === 'call').length >= 12, `${streamEvents.length} events`);
console.log(types.join('\n'));
const byCall = {};
for (const e of streamEvents.filter((e) => e.type === 'call')) (byCall[e.call.external_call_id] ||= []).push(e.call.status);
const inOrder = Object.values(byCall).every((s) => s.join(',') === 'dialing,connected,ended,completed');
check('stream: every call arrives as dialing → connected → ended → completed', inOrder, JSON.stringify(byCall));

streamAbort.abort();
await context.close();
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
