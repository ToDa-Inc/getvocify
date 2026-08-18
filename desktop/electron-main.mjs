import { app, BrowserWindow, desktopCapturer, ipcMain, session } from 'electron';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensureRuntimeDir, linuxChromiumSwitches, sanitizeSessionBusAddress } from './lib/launch.js';
import { feedS16le, resolveNativeLoopbackPlan } from './lib/system-audio.js';
import { createCompanionServer, listenLocal } from './server.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const bus = sanitizeSessionBusAddress(process.env.DBUS_SESSION_BUS_ADDRESS);
if (bus) process.env.DBUS_SESSION_BUS_ADDRESS = bus;
else delete process.env.DBUS_SESSION_BUS_ADDRESS;
process.env.XDG_RUNTIME_DIR = ensureRuntimeDir();

app.disableHardwareAcceleration();
for (const flag of linuxChromiumSwitches()) {
  app.commandLine.appendSwitch(flag);
}

let mainWindow = null;
let nativeCapture = null;
let nativeLeftover = Buffer.alloc(0);

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

function createWindow(url) {
  const win = new BrowserWindow({
    width: 440,
    height: 760,
    minWidth: 380,
    minHeight: 600,
    backgroundColor: '#f7f4ee',
    title: 'Vocify Companion',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });
  win.once('ready-to-show', () => win.show());
  win.loadURL(url);
  mainWindow = win;
  win.on('closed', () => {
    if (mainWindow === win) mainWindow = null;
    stopNativeCapture();
  });
  return win;
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

app.on('gpu-process-crashed', () => {
  console.warn('GPU process crashed; continuing with software rendering.');
});
app.on('child-process-gone', (_event, details) => {
  if (details?.type === 'GPU') {
    console.warn('GPU child process gone; window stays open.');
  }
});

app.whenReady().then(async () => {
  session.defaultSession.setDisplayMediaRequestHandler((request, callback) => {
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
  const url = await listenLocal(server);
  createWindow(url);
  app.on('before-quit', () => stopNativeCapture());
  console.log(`Vocify Companion is running at ${url}`);
  console.log('Keep this terminal open. D-Bus warnings on Linux are harmless.');

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow(url);
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
