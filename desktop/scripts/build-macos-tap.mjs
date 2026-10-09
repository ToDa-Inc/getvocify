import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const optional = process.argv.includes('--optional');
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const dir = path.join(root, 'native', 'macos-tap');
const out = path.join(dir, 'vocify-tap');
const source = path.join(dir, 'main.swift');

if (process.platform !== 'darwin') {
  if (!optional) console.log('Skipping vocify-tap (not macOS).');
  process.exit(0);
}

const swiftc = spawnSync('which', ['swiftc'], { encoding: 'utf8' });
if (swiftc.status !== 0) {
  if (optional) process.exit(0);
  console.error('swiftc is required to build vocify-tap.');
  process.exit(1);
}

const result = spawnSync(
  'swiftc',
  [
    '-O',
    '-o',
    out,
    source,
    '-framework',
    'ScreenCaptureKit',
    '-framework',
    'AVFoundation',
    '-framework',
    'CoreMedia',
    '-framework',
    'AudioToolbox',
  ],
  { stdio: 'inherit' },
);
if (result.status !== 0) {
  if (optional) {
    console.warn('vocify-tap compile failed; Chromium loopback will be used.');
    process.exit(0);
  }
  process.exit(result.status || 1);
}
fs.chmodSync(out, 0o755);
console.log(`Built ${out}`);
