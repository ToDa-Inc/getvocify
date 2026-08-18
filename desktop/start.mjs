import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { companionProcess, ensureRuntimeDir, shouldPreferWebUi } from './lib/launch.js';

if (shouldPreferWebUi()) {
  await import('./server.mjs');
} else {
  const require = createRequire(import.meta.url);
  const electronPath = require('electron');
  const { cmd, args } = companionProcess({ electronPath, dbusLaunch: 'dbus-launch' });
  const env = { ...process.env };
  env.XDG_RUNTIME_DIR = ensureRuntimeDir({ existing: env.XDG_RUNTIME_DIR });
  const child = spawn(cmd, args, {
    stdio: 'inherit',
    env,
    cwd: fileURLToPath(new URL('.', import.meta.url)),
  });
  child.on('error', (err) => {
    console.error('Failed to start Vocify Companion:', err.message);
    process.exit(1);
  });
  child.on('exit', (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    process.exit(code ?? 0);
  });
}
