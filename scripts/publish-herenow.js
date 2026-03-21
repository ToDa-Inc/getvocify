#!/usr/bin/env node
/**
 * Publish Vocify deck to here.now
 * Docs: https://here.now/docs
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const API = 'https://here.now/api/v1';

async function publish() {
  const htmlPath = path.join(ROOT, 'vocify_deck.html');
  const logoPath = path.join(ROOT, 'logo.png');

  const html = fs.readFileSync(htmlPath);
  const logo = fs.readFileSync(logoPath);

  const files = [
    { path: 'index.html', size: html.length, contentType: 'text/html; charset=utf-8' },
    { path: 'logo.png', size: logo.length, contentType: 'image/png' },
  ];

  const res = await fetch(`${API}/publish`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-HereNow-Client': 'cursor/publish-script',
    },
    body: JSON.stringify({
      files,
      viewer: {
        title: 'Vocify Deck',
        description: 'Presentación Vocify - Deja de escribir notas. Empieza a hablar.',
      },
    }),
  });

  if (!res.ok) {
    throw new Error(`Create failed: ${res.status} ${await res.text()}`);
  }

  const data = await res.json();
  const { siteUrl, upload, claimUrl, claimToken, expiresAt, anonymous } = data;

  for (const u of upload.uploads) {
    const body = u.path === 'index.html' ? html : logo;
    const putRes = await fetch(u.url, {
      method: 'PUT',
      headers: { 'Content-Type': u.headers['Content-Type'] },
      body,
    });
    if (!putRes.ok) {
      throw new Error(`Upload ${u.path} failed: ${putRes.status}`);
    }
  }

  const finalizeRes = await fetch(upload.finalizeUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ versionId: upload.versionId }),
  });

  if (!finalizeRes.ok) {
    throw new Error(`Finalize failed: ${finalizeRes.status} ${await finalizeRes.text()}`);
  }

  console.log('\n✅ Published to here.now\n');
  console.log('Live URL:', siteUrl);
  if (anonymous && claimUrl) {
    console.log('\n⚠️  Anonymous site — expires in 24h. To keep it permanently:');
    console.log('Claim URL:', claimUrl);
    console.log('(Save the claim URL and visit it to create an account and keep the site)');
  }
  return siteUrl;
}

publish().catch((err) => {
  console.error(err);
  process.exit(1);
});
