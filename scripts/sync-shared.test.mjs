import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { syncShared } from './sync-shared.mjs';

function sandbox({ desktop = true } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'shared-'));
  mkdirSync(join(root, 'shared/ui/components'), { recursive: true });
  writeFileSync(join(root, 'shared/ui/html.js'), 'export const a = 1;\n');
  writeFileSync(join(root, 'shared/ui/components/followup.js'), 'export const b = 2;\n');
  writeFileSync(join(root, 'shared/ui/ui.test.js'), '// tests stay home\n');
  mkdirSync(join(root, 'chrome-extension'), { recursive: true });
  if (desktop) mkdirSync(join(root, 'desktop/renderer'), { recursive: true });
  return root;
}

test('copies shared/ui into both vanilla surfaces, without tests', () => {
  const root = sandbox();
  assert.deepEqual(syncShared({ root, env: {} }).synced, ['extension', 'desktop']);
  assert.equal(readFileSync(join(root, 'chrome-extension/shared/ui/components/followup.js'), 'utf8'), 'export const b = 2;\n');
  assert.ok(existsSync(join(root, 'desktop/renderer/shared/ui/html.js')));
  assert.ok(!existsSync(join(root, 'chrome-extension/shared/ui/ui.test.js')));
  assert.deepEqual(syncShared({ root, check: true, env: {} }).stale, []);
});

test('--check catches an edited copy and a stray file', () => {
  const root = sandbox();
  syncShared({ root, env: {} });
  writeFileSync(join(root, 'chrome-extension/shared/ui/html.js'), 'edited');
  writeFileSync(join(root, 'desktop/renderer/shared/ui/stray.js'), 'x');
  assert.deepEqual(syncShared({ root, check: true, env: {} }).stale, ['extension', 'desktop']);
  syncShared({ root, env: {} });
  assert.ok(!existsSync(join(root, 'desktop/renderer/shared/ui/stray.js')), 'resync removes strays');
});

test('a missing desktop is skipped; VOCIFY_DESKTOP_DIR points at a sibling repo', () => {
  const root = sandbox({ desktop: false });
  assert.deepEqual(syncShared({ root, env: {} }).skipped, ['desktop']);
  const sibling = mkdtempSync(join(tmpdir(), 'desktop-'));
  mkdirSync(join(sibling, 'renderer'), { recursive: true });
  assert.ok(syncShared({ root, env: { VOCIFY_DESKTOP_DIR: sibling } }).synced.includes('desktop'));
  assert.ok(existsSync(join(sibling, 'renderer/shared/ui/components/followup.js')));
});
