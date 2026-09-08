import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

const manifest = JSON.parse(
  readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), '..', 'manifest.json'),
    'utf8',
  ),
);

describe('Telnyx host permissions', () => {
  it('allows the WebRTC signaling and ICE hosts the vendored SDK uses', () => {
    const hosts = manifest.host_permissions || [];
    assert.ok(hosts.includes('https://*.telnyx.com/*'));
    assert.ok(hosts.includes('wss://*.telnyx.com/*'));
  });
});
