import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  applyPermissionSnapshot,
  listenPermissionGate,
  normalizeAccessStatus,
  permissionAction,
  permissionCopy,
  settingsDeepLinks,
} from './permissions.js';

describe('permissions', () => {
  it('normalizes native permission snapshots', () => {
    assert.deepEqual(applyPermissionSnapshot({ microphone: 'authorized', systemAudio: 'granted' }), {
      platform: 'darwin',
      microphone: 'authorized',
      systemAudio: 'authorized',
    });
    assert.deepEqual(applyPermissionSnapshot(null), {
      platform: 'darwin',
      microphone: 'never_requested',
      systemAudio: 'never_requested',
    });
  });

  it('maps Electron/TCC statuses', () => {
    assert.equal(normalizeAccessStatus('granted'), 'authorized');
    assert.equal(normalizeAccessStatus('denied'), 'denied');
    assert.equal(normalizeAccessStatus('not-determined'), 'never_requested');
  });

  it('gates listen on macOS until mic and screen-audio are authorized', () => {
    assert.deepEqual(
      listenPermissionGate({ platform: 'darwin', microphone: 'authorized', systemAudio: 'never_requested' }),
      { ok: false, reason: 'no_system_audio' },
    );
    assert.equal(
      listenPermissionGate({ platform: 'darwin', microphone: 'authorized', systemAudio: 'authorized' }).ok,
      true,
    );
    assert.equal(listenPermissionGate({ platform: 'linux' }).ok, true);
  });

  it('opens Settings after a denial, otherwise requests', () => {
    assert.equal(permissionAction('never_requested'), 'request');
    assert.equal(permissionAction('denied'), 'open_settings');
    assert.equal(permissionAction('authorized'), 'none');
  });

  it('explains Screen Recording as system audio, not a screen grab', () => {
    assert.match(permissionCopy('systemAudio').enableBody, /does not capture your screen/i);
    assert.match(settingsDeepLinks('systemAudio')[0], /Privacy_ScreenCapture/);
    assert.match(settingsDeepLinks('microphone')[1], /Privacy_Microphone/);
  });
});
