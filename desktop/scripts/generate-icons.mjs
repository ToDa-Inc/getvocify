import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const brand = path.join(root, 'brand', 'icon-512.png');
if (!fs.existsSync(brand)) {
  console.error('Missing brand/icon-512.png (official Vocify mark).');
  process.exit(1);
}
fs.mkdirSync(path.join(root, 'build'), { recursive: true });
fs.copyFileSync(brand, path.join(root, 'build', 'icon.png'));
fs.copyFileSync(brand, path.join(root, 'renderer', 'icon.png'));
console.log('Copied official Vocify icon to build/ and renderer/.');
