import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { createCompanionServer, listenLocal } from '../server.mjs';

describe('companion static server', () => {
  it('serves the renderer shell and JS modules', async () => {
    const server = createCompanionServer();
    const url = await listenLocal(server);
    try {
      const html = await fetch(url).then((r) => r.text());
      assert.match(html, /Vocify Companion/);
      const overlay = await fetch(url.replace(/index\.html$/, 'overlay.html')).then((r) => r.text());
      assert.match(overlay, /Listening to the call/);
      const jsUrl = url.replace(/index\.html$/, 'app.js');
      const js = await fetch(jsUrl);
      assert.equal(js.status, 200);
      assert.match(js.headers.get('content-type') || '', /javascript/);
    } finally {
      server.close();
    }
  });
});
