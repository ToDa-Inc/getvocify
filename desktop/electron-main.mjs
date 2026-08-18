import { app, BrowserWindow, desktopCapturer, session } from 'electron';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensureRuntimeDir, linuxChromiumSwitches, sanitizeSessionBusAddress } from './lib/launch.js';
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
}

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
  console.log(`Vocify Companion is running at ${url}`);
  console.log('Keep this terminal open. D-Bus warnings on Linux are harmless.');

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow(url);
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
