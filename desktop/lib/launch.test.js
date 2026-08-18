import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  companionProcess,
  linuxChromiumSwitches,
  mimeFor,
  ensureRuntimeDir,
  sanitizeSessionBusAddress,
  shouldPreferWebUi,
} from './launch.js';

describe('launch', () => {
  it('disables GPU and sandbox on Linux so Chromium can start without D-Bus or a GPU', () => {
    const flags = linuxChromiumSwitches({ platform: 'linux' });
    assert.ok(flags.includes('disable-gpu'));
    assert.ok(flags.includes('no-sandbox'));
    assert.equal(linuxChromiumSwitches({ platform: 'darwin' }).includes('no-sandbox'), false);
  });

  it('drops empty or unparseable D-Bus addresses (Chromium "Unknown address type")', () => {
    assert.equal(sanitizeSessionBusAddress(''), null);
    assert.equal(sanitizeSessionBusAddress(':1'), null);
    assert.equal(sanitizeSessionBusAddress('unix:path=/tmp/bus'), 'unix:path=/tmp/bus');
  });

  it('prefers the web UI when Linux has no display', () => {
    assert.equal(shouldPreferWebUi({ platform: 'linux', display: '', wayland: '', forceWeb: false }), true);
    assert.equal(shouldPreferWebUi({ platform: 'linux', display: ':1', wayland: '', forceWeb: false }), false);
    assert.equal(shouldPreferWebUi({ platform: 'darwin', display: '', forceWeb: false }), false);
    assert.equal(shouldPreferWebUi({ platform: 'linux', display: ':1', forceWeb: true }), true);
  });

  it('wraps Linux Electron in dbus-launch when there is no session bus', () => {
    const linux = companionProcess({
      platform: 'linux',
      electronPath: '/app/electron',
      dbusLaunch: 'dbus-launch',
      busAddress: '',
    });
    assert.equal(linux.cmd, 'dbus-launch');
    assert.ok(linux.args.includes('--disable-gpu'));
    const mac = companionProcess({
      platform: 'darwin',
      electronPath: '/app/electron',
      dbusLaunch: 'dbus-launch',
      busAddress: '',
    });
    assert.equal(mac.cmd, '/app/electron');
  });

  it('uses a user-owned runtime dir when XDG_RUNTIME_DIR is root-owned /tmp', () => {
    const created = [];
    const dir = ensureRuntimeDir({
      existing: '/tmp',
      uid: 1000,
      tmpdir: '/var/tmp',
      mkdir: (d) => created.push(d),
      stat: () => ({ uid: 0 }),
    });
    assert.equal(dir, '/var/tmp/vocify-runtime-1000');
    assert.deepEqual(created, ['/var/tmp/vocify-runtime-1000']);
  });

  it('serves JS modules with the javascript MIME type', () => {
    assert.match(mimeFor('/renderer/app.js'), /javascript/);
    assert.match(mimeFor('/renderer/index.html'), /html/);
  });
});
