#!/usr/bin/env node
// A Chrome extension cannot load files outside its own folder, and the desktop
// renderer ships as its own bundle, so shared/ui is copied into both vanilla
// surfaces. Copies are committed; --check fails CI when they drift.
// The web app imports shared/ui directly through a Vite alias and needs no copy.
// Usage: node scripts/sync-shared.mjs [--check]   (VOCIFY_DESKTOP_DIR for a sibling repo)
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SOURCE = 'shared/ui';

function listFiles(dir) {
  if (!existsSync(dir)) return [];
  const out = [];
  const walk = (current) => {
    for (const name of readdirSync(current)) {
      const full = join(current, name);
      if (statSync(full).isDirectory()) walk(full);
      else out.push(relative(dir, full));
    }
  };
  walk(dir);
  return out.sort();
}

export function destinations(root, env = process.env) {
  const desktop = env.VOCIFY_DESKTOP_DIR ? resolve(root, env.VOCIFY_DESKTOP_DIR) : join(root, 'desktop');
  return [
    { key: 'extension', dir: join(root, 'chrome-extension/shared/ui'), anchor: join(root, 'chrome-extension') },
    { key: 'desktop', dir: join(desktop, 'renderer/shared/ui'), anchor: join(desktop, 'renderer') },
  ];
}

export function syncShared({ root, check = false, env = process.env }) {
  const src = join(root, SOURCE);
  const files = listFiles(src).filter((f) => !f.endsWith('.test.js'));
  const report = { synced: [], stale: [], skipped: [] };
  for (const dest of destinations(root, env)) {
    if (!existsSync(dest.anchor)) {
      report.skipped.push(dest.key);
      continue;
    }
    const present = listFiles(dest.dir);
    const drift =
      present.join('\n') !== files.join('\n') ||
      files.some((f) => readFileSync(join(dest.dir, f), 'utf8') !== readFileSync(join(src, f), 'utf8'));
    if (!drift) continue;
    if (check) {
      report.stale.push(dest.key);
      continue;
    }
    rmSync(dest.dir, { recursive: true, force: true });
    for (const f of files) {
      mkdirSync(dirname(join(dest.dir, f)), { recursive: true });
      writeFileSync(join(dest.dir, f), readFileSync(join(src, f)));
    }
    report.synced.push(dest.key);
  }
  return report;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const check = process.argv.includes('--check');
  const report = syncShared({ root, check });
  for (const key of report.skipped) console.warn(`shared: skipped ${key} (surface not found)`);
  if (check && report.stale.length) {
    console.error(`shared: stale → ${report.stale.join(', ')}. Run: node scripts/sync-shared.mjs`);
    process.exit(1);
  }
  if (!check) console.log(report.synced.length ? `shared: synced ${report.synced.join(', ')}` : 'shared: up to date');
}
