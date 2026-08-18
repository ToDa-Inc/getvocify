import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mimeFor } from './lib/launch.js';

const root = path.dirname(fileURLToPath(import.meta.url));

function safeJoin(urlPath) {
  const decoded = decodeURIComponent((urlPath || '/').split('?')[0]);
  const rel = decoded === '/' ? '/renderer/index.html' : decoded;
  const resolved = path.resolve(root, `.${rel}`);
  if (!resolved.startsWith(root)) return null;
  return resolved;
}

export function createCompanionServer() {
  return http.createServer((req, res) => {
    const filePath = safeJoin(req.url || '/');
    if (!filePath) {
      res.writeHead(403);
      res.end('Forbidden');
      return;
    }
    fs.readFile(filePath, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end('Not found');
        return;
      }
      res.writeHead(200, { 'Content-Type': mimeFor(filePath) });
      res.end(data);
    });
  });
}

export function listenLocal(server, port = 0) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => {
      const addr = server.address();
      resolve(`http://127.0.0.1:${addr.port}/renderer/index.html`);
    });
  });
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const server = createCompanionServer();
  const url = await listenLocal(server, Number(process.env.PORT) || 3847);
  console.log(`Vocify Companion (browser): ${url}`);
}
