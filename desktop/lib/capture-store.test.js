import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';
import { CaptureStore, DiskFullError } from './capture-store.js';

function store() {
  const root = mkdtempSync(join(tmpdir(), 'vocify-cap-'));
  return { root, store: new CaptureStore(root), cleanup: () => rmSync(root, { recursive: true, force: true }) };
}

test('restart recovers the manifest and audio before remote confirmation', () => {
  const ctx = store();
  try {
    ctx.store.begin('cap-local-1', { startedAt: '2026-09-22T08:00:00Z' });
    ctx.store.append('cap-local-1', 'mic', Buffer.from('chunk-a'));
    const reopened = new CaptureStore(ctx.root);
    const pending = reopened.pending();
    assert.equal(pending.length, 1);
    assert.equal(pending[0].clientCaptureId, 'cap-local-1');
    assert.equal(pending[0].remoteConfirmed, false);
    const audio = readFileSync(pending[0].channels.mic.path);
    assert.equal(audio.toString(), 'chunk-a');
    assert.throws(() => reopened.discard('cap-local-1'), /confirmación remota/);
  } finally {
    ctx.cleanup();
  }
});

test('a missing channel stays partial and disk full keeps the previous audio', () => {
  const ctx = store();
  try {
    ctx.store.begin('cap-local-1', { startedAt: '2026-09-22T08:00:00Z' });
    ctx.store.append('cap-local-1', 'mic', Buffer.from('ok'));
    ctx.store.noteChannelAbsent('cap-local-1', 'system', 'permission');
    const view = ctx.store.read('cap-local-1');
    assert.equal(view.audioStatus, 'partial');
    assert.equal(view.channelsComplete, false);
    assert.equal(view.channels.system.absent, true);

    const failing = new CaptureStore(ctx.root, {
      appendFile(path, chunk) {
        const err = new Error('no space');
        err.code = 'ENOSPC';
        throw err;
      },
    });
    assert.throws(() => failing.append('cap-local-1', 'mic', Buffer.from('more')), DiskFullError);
    assert.equal(readFileSync(view.channels.mic.path).toString(), 'ok');
  } finally {
    ctx.cleanup();
  }
});

test('discard removes local files only after remote confirmation', () => {
  const ctx = store();
  try {
    ctx.store.begin('cap-local-1', { startedAt: '2026-09-22T08:00:00Z' });
    ctx.store.append('cap-local-1', 'mic', Buffer.from('ok'));
    ctx.store.confirmRemote('cap-local-1');
    ctx.store.discard('cap-local-1');
    assert.deepEqual(ctx.store.pending(), []);
  } finally {
    ctx.cleanup();
  }
});
