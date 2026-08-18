import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export function linuxChromiumSwitches({ platform = process.platform } = {}) {
  if (platform !== 'linux') return [];
  return ['disable-gpu', 'disable-gpu-compositing', 'disable-dev-shm-usage', 'no-sandbox'];
}

export function sanitizeSessionBusAddress(addr) {
  if (!addr || typeof addr !== 'string') return null;
  const trimmed = addr.trim();
  if (!/^(unix|tcp|nonce-tcp|autolaunch):/.test(trimmed)) return null;
  return trimmed;
}

export function shouldPreferWebUi({
  platform = process.platform,
  display = process.env.DISPLAY,
  wayland = process.env.WAYLAND_DISPLAY,
  forceWeb = process.env.VOCIFY_COMPANION_WEB === '1',
} = {}) {
  if (forceWeb) return true;
  if (platform !== 'linux') return false;
  return !display && !wayland;
}

export function companionProcess({
  platform = process.platform,
  electronPath = 'electron',
  dbusLaunch = 'dbus-launch',
  busAddress = process.env.DBUS_SESSION_BUS_ADDRESS,
} = {}) {
  const flags = linuxChromiumSwitches({ platform }).map((s) => `--${s}`);
  const args = [...flags, '.'];
  if (platform === 'linux' && dbusLaunch && !sanitizeSessionBusAddress(busAddress)) {
    return { cmd: dbusLaunch, args: ['--exit-with-session', electronPath, ...args] };
  }
  return { cmd: electronPath, args };
}

export function ensureRuntimeDir({
  existing = process.env.XDG_RUNTIME_DIR,
  uid = typeof process.getuid === 'function' ? process.getuid() : 0,
  tmpdir = os.tmpdir(),
  mkdir = (dir, opts) => fs.mkdirSync(dir, opts),
  stat = (dir) => fs.statSync(dir),
} = {}) {
  if (existing) {
    try {
      const st = stat(existing);
      if (typeof st.uid !== 'number' || st.uid === uid) return existing;
    } catch {
      // fall through and create a private dir
    }
  }
  const dir = path.join(tmpdir, `vocify-runtime-${uid}`);
  mkdir(dir, { recursive: true, mode: 0o700 });
  return dir;
}

export function mimeFor(filePath) {
  if (filePath.endsWith('.html')) return 'text/html; charset=utf-8';
  if (filePath.endsWith('.css')) return 'text/css; charset=utf-8';
  if (filePath.endsWith('.js') || filePath.endsWith('.mjs')) return 'text/javascript; charset=utf-8';
  if (filePath.endsWith('.json')) return 'application/json; charset=utf-8';
  if (filePath.endsWith('.svg')) return 'image/svg+xml';
  return 'application/octet-stream';
}
