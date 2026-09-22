import {
  app,
  BrowserWindow,
  Menu,
  Tray,
  desktopCapturer,
  ipcMain,
  nativeImage,
  screen,
  session,
  shell,
  systemPreferences,
} from 'electron';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensureRuntimeDir, linuxChromiumSwitches, sanitizeSessionBusAddress } from './lib/launch.js';
import { feedS16le, resolveNativeLoopbackPlan, vocifyTapPath } from './lib/system-audio.js';
import { CaptureStore } from './lib/capture-store.js';
import {
  dashboardMemosUrl,
  overlayBoundsForState,
  overlayShellState,
  shouldQuitOnLastWindow,
  trayMenuTemplate,
  WINDOW_SIZE,
} from './lib/shell.js';
import { normalizeAccessStatus, PERMISSION, settingsDeepLinks } from './lib/permissions.js';
import { createCompanionServer, listenLocal } from './server.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const bus = sanitizeSessionBusAddress(process.env.DBUS_SESSION_BUS_ADDRESS);
if (bus) process.env.DBUS_SESSION_BUS_ADDRESS = bus;
else delete process.env.DBUS_SESSION_BUS_ADDRESS;
process.env.XDG_RUNTIME_DIR = ensureRuntimeDir();

if (process.platform === 'linux') {
  app.disableHardwareAcceleration();
  for (const flag of linuxChromiumSwitches()) {
    app.commandLine.appendSwitch(flag);
  }
}

let mainWindow = null;
let overlayWindow = null;
let tray = null;
let rendererUrl = '';
let overlayUrl = '';
let isQuitting = false;
let nativeCapture = null;
let nativeLeftover = Buffer.alloc(0);
let shellState = { listening: false, loggedIn: false, apiBase: '', lastLine: '' };

function stopNativeCapture() {
  const child = nativeCapture;
  nativeCapture = null;
  nativeLeftover = Buffer.alloc(0);
  if (!child) return;
  try {
    child.stdout?.destroy();
  } catch {
    /* ignore */
  }
  try {
    child.kill('SIGTERM');
  } catch {
    /* ignore */
  }
}

function webPrefs() {
  return {
    preload: path.join(__dirname, 'preload.cjs'),
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: false,
  };
}

function showMainWindow() {
  if (!mainWindow) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

function revealWindow(win) {
  if (!win || win.isDestroyed()) return;
  if (process.platform === 'darwin') app.dock?.show();
  win.show();
  win.moveTop();
  win.focus();
}

function createWindow() {
  const win = new BrowserWindow({
    width: WINDOW_SIZE.compact.width,
    height: WINDOW_SIZE.compact.height,
    minWidth: 380,
    minHeight: 640,
    backgroundColor: '#f7f4ee',
    title: 'Vocify Companion',
    icon: path.join(__dirname, 'build', 'icon.png'),
    show: true,
    autoHideMenuBar: true,
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    trafficLightPosition: { x: 14, y: 16 },
    webPreferences: webPrefs(),
  });
  win.once('ready-to-show', () => revealWindow(win));
  win.webContents.on('did-fail-load', (_e, code, desc) => {
    console.error(`Companion window failed to load (${code}): ${desc}`);
    revealWindow(win);
  });
  setTimeout(() => revealWindow(win), 1500);
  win.loadURL(rendererUrl);
  mainWindow = win;
  win.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      win.hide();
    }
  });
  win.on('closed', () => {
    if (mainWindow === win) mainWindow = null;
    if (!shellState.listening) stopNativeCapture();
  });
  return win;
}

function syncOverlayBounds() {
  if (!overlayWindow) return;
  const display = screen.getPrimaryDisplay();
  overlayWindow.setBounds(overlayBoundsForState(shellState, { workArea: display.workArea }));
}

function createOverlay() {
  const display = screen.getPrimaryDisplay();
  const bounds = overlayBoundsForState(shellState, { workArea: display.workArea });
  const win = new BrowserWindow({
    ...bounds,
    frame: false,
    transparent: true,
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    focusable: true,
    hasShadow: false,
    show: false,
    webPreferences: webPrefs(),
  });
  win.setAlwaysOnTop(true, 'floating');
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.loadURL(overlayUrl);
  overlayWindow = win;
  win.on('closed', () => {
    if (overlayWindow === win) overlayWindow = null;
  });
  return win;
}

function showOverlay() {
  if (!overlayWindow) createOverlay();
  const display = screen.getPrimaryDisplay();
  syncOverlayBounds();
  overlayWindow.showInactive();
}

function hideOverlay() {
  overlayWindow?.hide();
}

function sendCommand(name) {
  if (name === 'show') {
    showMainWindow();
    return;
  }
  if (name === 'dashboard') {
    shell.openExternal(dashboardMemosUrl(shellState.apiBase));
    return;
  }
  if (name === 'quit') {
    isQuitting = true;
    app.quit();
    return;
  }
  showMainWindow();
  mainWindow?.webContents.send('shell:command', name);
}

function rebuildTrayMenu() {
  if (!tray) return;
  const template = trayMenuTemplate(shellState).map((item) => {
    if (item.type === 'separator') return { type: 'separator' };
    return {
      label: item.label,
      enabled: item.enabled !== false,
      click: () => sendCommand(item.id),
    };
  });
  tray.setContextMenu(Menu.buildFromTemplate(template));
  tray.setToolTip(shellState.listening ? 'Vocify · Listening' : 'Vocify Companion');
}

function createTray() {
  try {
    const iconPath = path.join(__dirname, 'build', 'icon.png');
    const image = nativeImage.createFromPath(iconPath);
    const icon = image.isEmpty() ? nativeImage.createEmpty() : image.resize({ width: 18, height: 18 });
    tray = new Tray(icon);
    tray.on('click', () => showMainWindow());
    rebuildTrayMenu();
  } catch (err) {
    console.warn('Tray icon unavailable; window still opens.', err?.message || err);
  }
}

ipcMain.handle('system-audio:start', async () => {
  stopNativeCapture();
  const tap = vocifyTapPath({
    platform: process.platform,
    appRoot: __dirname,
    resourcesPath: process.resourcesPath,
  });
  const plan = resolveNativeLoopbackPlan({ vocifyTap: tap });
  if (!plan) return { ok: false, reason: 'unavailable' };
  try {
    const child = spawn(plan.cmd, plan.args, { stdio: ['ignore', 'pipe', 'pipe'] });
    nativeCapture = child;
    nativeLeftover = Buffer.alloc(0);
    child.stdout.on('data', (chunk) => {
      nativeLeftover = feedS16le(chunk, nativeLeftover, (pcm) => {
        mainWindow?.webContents.send('system-audio:pcm', pcm);
      });
    });
    child.stderr?.on('data', (chunk) => {
      const text = String(chunk).trim();
      if (text) console.warn(`[system-audio ${plan.backend}]`, text);
    });
    const failed = await new Promise((resolve) => {
      const timer = setTimeout(() => resolve(false), 400);
      child.once('error', () => {
        clearTimeout(timer);
        resolve(true);
      });
      child.once('exit', () => {
        clearTimeout(timer);
        resolve(true);
      });
    });
    if (failed || nativeCapture !== child) {
      stopNativeCapture();
      return { ok: false, reason: 'unavailable' };
    }
    child.on('exit', () => {
      if (nativeCapture === child) nativeCapture = null;
    });
    return { ok: true, backend: plan.backend };
  } catch {
    stopNativeCapture();
    return { ok: false, reason: 'unavailable' };
  }
});

ipcMain.handle('system-audio:stop', () => {
  stopNativeCapture();
  return { ok: true };
});

ipcMain.handle('shell:resize', (_event, size) => {
  const next = size === 'review' ? WINDOW_SIZE.review : WINDOW_SIZE.compact;
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setSize(next.width, next.height, true);
  }
  return { ok: true, ...next };
});

function permissionSnapshot() {
  if (process.platform !== 'darwin' || !systemPreferences.getMediaAccessStatus) {
    return { platform: process.platform, microphone: 'authorized', systemAudio: 'authorized' };
  }
  return {
    platform: 'darwin',
    microphone: normalizeAccessStatus(systemPreferences.getMediaAccessStatus('microphone')),
    systemAudio: normalizeAccessStatus(systemPreferences.getMediaAccessStatus('screen')),
  };
}

ipcMain.handle('permissions:status', () => permissionSnapshot());

ipcMain.handle('permissions:request', async (_event, type) => {
  if (process.platform === 'darwin' && type === PERMISSION.microphone && systemPreferences.askForMediaAccess) {
    try {
      await systemPreferences.askForMediaAccess('microphone');
    } catch {
      /* user can retry */
    }
  }
  if (process.platform === 'darwin' && type === PERMISSION.systemAudio) {
    try {
      await desktopCapturer.getSources({ types: ['screen'] });
    } catch {
      /* TCC prompt or already denied */
    }
  }
  return permissionSnapshot();
});

ipcMain.handle('permissions:open', async (_event, type) => {
  for (const url of settingsDeepLinks(type === PERMISSION.microphone ? PERMISSION.microphone : PERMISSION.systemAudio)) {
    try {
      await shell.openExternal(url);
      break;
    } catch {
      /* try the older Settings URL */
    }
  }
  return permissionSnapshot();
});

function applyShellStatePatch(state) {
  shellState = { ...shellState, ...state };
  for (const key of ['kind', 'playbookReady', 'assistEnabled', 'card', 'checklist']) {
    if (Object.prototype.hasOwnProperty.call(state, key) && state[key] == null) {
      delete shellState[key];
    }
  }
  if (Object.prototype.hasOwnProperty.call(state, 'evidenceRefs')) {
    shellState.evidenceRefs = Array.isArray(state.evidenceRefs) ? state.evidenceRefs : [];
  }
}

ipcMain.on('shell:state', (_event, state) => {
  applyShellStatePatch(state);
  overlayWindow?.webContents.send('overlay:state', overlayShellState(shellState));
  syncOverlayBounds();
  rebuildTrayMenu();
});

ipcMain.on('shell:command', (_event, name) => sendCommand(name));

ipcMain.handle('overlay:show', () => {
  showOverlay();
  return { ok: true };
});

ipcMain.handle('overlay:hide', () => {
  hideOverlay();
  return { ok: true };
});

ipcMain.handle('shell:open-external', (_event, url) => {
  if (typeof url !== 'string' || !/^(https?:\/\/|mailto:)/i.test(url)) return { ok: false };
  shell.openExternal(url);
  return { ok: true };
});

let captureStore;

function captures() {
  if (!captureStore) {
    captureStore = new CaptureStore(path.join(app.getPath('userData'), 'captures'));
  }
  return captureStore;
}

ipcMain.handle('capture:begin', (_event, payload) => {
  const id = payload?.clientCaptureId;
  if (!id) return { ok: false, error: 'clientCaptureId required' };
  return { ok: true, manifest: captures().begin(id, payload) };
});

ipcMain.handle('capture:append', (_event, payload) => {
  try {
    const chunk = Buffer.from(payload?.chunk || []);
    const manifest = captures().append(payload.clientCaptureId, payload.channel, chunk);
    return { ok: true, manifest };
  } catch (err) {
    return { ok: false, error: err.message, code: err.code || 'append_failed' };
  }
});

ipcMain.handle('capture:channel-absent', (_event, payload) => {
  const manifest = captures().noteChannelAbsent(payload.clientCaptureId, payload.channel, payload.reason);
  return { ok: true, manifest };
});

ipcMain.handle('capture:pending', () => ({ ok: true, items: captures().pending() }));

ipcMain.handle('capture:confirm', (_event, clientCaptureId) => {
  return { ok: true, manifest: captures().confirmRemote(clientCaptureId) };
});

ipcMain.handle('capture:discard', (_event, clientCaptureId) => {
  try {
    captures().discard(clientCaptureId);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

ipcMain.handle('saas:request', async (_event, payload) => {
  const { base, path: apiPath, method, headers, body } = payload || {};
  if (!isAllowedApiBase(base)) {
    console.warn('[saas] blocked API base', base);
    return { ok: false, status: 0, data: {}, error: 'API base is not a Vocify host' };
  }
  const label = `${method || 'GET'} ${base}${apiPath || ''}`;
  console.log(`[saas] → ${label}`);
  try {
    const result = await proxyJsonRequest(fetch, { base, path: apiPath, method, headers, body });
    console.log(`[saas] ← ${result.status} ${label}${result.ok ? '' : ` ${result.error || ''}`}`);
    return result;
  } catch (err) {
    console.error(`[saas] failed ${label}:`, err?.message || err);
    return { ok: false, status: 0, data: {}, error: err?.message || 'Request failed' };
  }
});

app.on('gpu-process-crashed', () => {
  console.warn('GPU process crashed; continuing with software rendering.');
});
app.on('child-process-gone', (_event, details) => {
  if (details?.type === 'GPU') {
    console.warn('GPU child process gone; window stays open.');
  }
});

app.whenReady().then(async () => {
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    callback(['media', 'display-capture', 'audioCapture', 'mediaKeySystem'].includes(permission));
  });
  session.defaultSession.setDisplayMediaRequestHandler((_request, callback) => {
    desktopCapturer
      .getSources({ types: ['screen'] })
      .then((sources) => {
        const source = sources[0];
        if (!source) {
          callback({});
          return;
        }
        callback({ video: source, audio: 'loopback' });
      })
      .catch(() => callback({}));
  });

  const server = createCompanionServer();
  rendererUrl = await listenLocal(server);
  overlayUrl = rendererUrl.replace(/index\.html$/, 'overlay.html');
  if (process.platform === 'darwin') {
    Menu.setApplicationMenu(
      Menu.buildFromTemplate([
        { role: 'appMenu' },
        { role: 'editMenu' },
        { role: 'viewMenu' },
        { role: 'windowMenu' },
      ]),
    );
  }
  createWindow();
  createOverlay();
  createTray();
  const dockIcon = nativeImage.createFromPath(path.join(__dirname, 'build', 'icon.png'));
  if (process.platform === 'darwin' && !dockIcon.isEmpty()) {
    app.dock?.setIcon(dockIcon);
  }
  if (!app.isPackaged) {
    mainWindow?.webContents.openDevTools({ mode: 'detach' });
  }
  revealWindow(mainWindow);
  app.on('before-quit', () => {
    isQuitting = true;
    stopNativeCapture();
  });
  console.log(`Vocify Companion window should be visible.`);
  console.log(`UI also at ${rendererUrl}`);
  console.log('Look for Vocify in the Dock / menu bar. Keep this terminal open in dev.');

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else showMainWindow();
  });
});

app.on('window-all-closed', () => {
  if (shouldQuitOnLastWindow({ platform: process.platform, isQuitting })) app.quit();
});
