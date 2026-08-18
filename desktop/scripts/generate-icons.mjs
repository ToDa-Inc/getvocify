import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'build');

function crc32(buf) {
  return zlib.crc32(buf) >>> 0;
}

function chunk(tag, data) {
  const header = Buffer.from(tag);
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([header, data])));
  return Buffer.concat([len, header, data, crc]);
}

function writePng(filePath, width, height, rgba) {
  const raw = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y++) {
    const row = y * (width * 4 + 1);
    raw[row] = 0;
    rgba.copy(raw, row + 1, y * width * 4, (y + 1) * width * 4);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  const png = Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ]);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, png);
}

function roundedRectMask(x, y, size, radius) {
  const dx = Math.min(x, size - 1 - x);
  const dy = Math.min(y, size - 1 - y);
  if (dx >= radius || dy >= radius) return true;
  const cx = radius - dx;
  const cy = radius - dy;
  return cx * cx + cy * cy <= radius * radius;
}

function paintIcon(size, { tray = false } = {}) {
  const rgba = Buffer.alloc(size * size * 4);
  const radius = Math.round(size * 0.22);
  const beige = [107, 93, 79, 255];
  const cream = [247, 244, 238, 255];
  const ink = [10, 10, 10, 255];
  const fill = tray ? ink : beige;
  const letter = tray ? [0, 0, 0, 255] : cream;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      const inside = tray ? true : roundedRectMask(x, y, size, radius);
      if (inside && !tray) {
        rgba[i] = fill[0];
        rgba[i + 1] = fill[1];
        rgba[i + 2] = fill[2];
        rgba[i + 3] = fill[3];
      }
    }
  }
  const thickness = Math.max(2, Math.round(size * 0.11));
  const topY = Math.round(size * 0.28);
  const botY = Math.round(size * 0.78);
  const leftX = Math.round(size * 0.28);
  const rightX = Math.round(size * 0.72);
  const midX = Math.round(size * 0.5);
  function stamp(x, y) {
    for (let dy = -thickness; dy <= thickness; dy++) {
      for (let dx = -Math.round(thickness * 0.45); dx <= Math.round(thickness * 0.45); dx++) {
        const px = x + dx;
        const py = y + dy;
        if (px < 0 || py < 0 || px >= size || py >= size) continue;
        const i = (py * size + px) * 4;
        rgba[i] = letter[0];
        rgba[i + 1] = letter[1];
        rgba[i + 2] = letter[2];
        rgba[i + 3] = 255;
      }
    }
  }
  const steps = size * 2;
  for (let s = 0; s <= steps; s++) {
    const t = s / steps;
    stamp(Math.round(leftX + (midX - leftX) * t), Math.round(topY + (botY - topY) * t));
    stamp(Math.round(rightX + (midX - rightX) * t), Math.round(topY + (botY - topY) * t));
  }
  return rgba;
}

writePng(path.join(root, 'icon.png'), 512, 512, paintIcon(512));
writePng(path.join(root, 'trayTemplate.png'), 16, 16, paintIcon(16, { tray: true }));
writePng(path.join(root, 'trayTemplate@2x.png'), 32, 32, paintIcon(32, { tray: true }));
console.log('Wrote companion icons to', root);
