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
import {
  dashboardMemosUrl,
  overlayBounds,
  shouldQuitOnLastWindow,
  trayMenuTemplate,
} from './lib/shell.js';
import { feedS16le, resolveNativeLoopbackPlan } from './lib/system-audio.js';
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

function createWindow() {
  const win = new BrowserWindow({
    width: 420,
    height: 780,
    minWidth: 380,
    minHeight: 640,
    backgroundColor: '#f7f4ee',
    title: 'Vocify Companion',
    show: false,
    autoHideMenuBar: true,
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    trafficLightPosition: { x: 14, y: 16 },
    webPreferences: webPrefs(),
  });
  win.once('ready-to-show', () => win.show());
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

function createOverlay() {
  const display = screen.getPrimaryDisplay();
  const bounds = overlayBounds({ workArea: display.workArea });
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
  overlayWindow.setBounds(overlayBounds({ workArea: display.workArea }));
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
  const iconFile = process.platform === 'darwin' ? 'trayTemplate.png' : 'icon.png';
  const iconPath = path.join(__dirname, 'build', iconFile);
  const image = nativeImage.createFromPath(iconPath);
  if (process.platform === 'darwin') image.setTemplateImage(true);
  tray = new Tray(image.isEmpty() ? nativeImage.createEmpty() : image.resize({ width: 18, height: 18 }));
  tray.on('click', () => showMainWindow());
  rebuildTrayMenu();
}

ipcMain.handle('system-audio:start', async () => {
  stopNativeCapture();
  const plan = resolveNativeLoopbackPlan();
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

ipcMain.on('shell:state', (_event, state) => {
  shellState = { ...shellState, ...state };
  overlayWindow?.webContents.send('overlay:state', shellState);
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
  if (typeof url === 'string' && /^https?:\/\//i.test(url)) shell.openExternal(url);
  return { ok: true };
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

  if (process.platform === 'darwin' && systemPreferences.askForMediaAccess) {
    try {
      await systemPreferences.askForMediaAccess('microphone');
    } catch {
      /* user can retry from Listen */
    }
  }

  const server = createCompanionServer();
  rendererUrl = await listenLocal(server);
  overlayUrl = rendererUrl.replace(/index\.html$/, 'overlay.html');
  if (process.platform === 'darwin') {
    Menu.setApplicationMenu(
      Menu.buildFromTemplate([{ role: 'appMenu' }, { role: 'editMenu' }, { role: 'windowMenu' }]),
    );
  }
  createWindow();
  createOverlay();
  createTray();
  app.on('before-quit', () => {
    isQuitting = true;
    stopNativeCapture();
  });
  console.log(`Vocify Companion is running at ${rendererUrl}`);
  console.log('Tray + overlay are on. Keep this terminal open in dev.');

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else showMainWindow();
  });
});

app.on('window-all-closed', () => {
  if (shouldQuitOnLastWindow({ platform: process.platform, isQuitting })) app.quit();
});
