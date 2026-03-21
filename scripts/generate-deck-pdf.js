#!/usr/bin/env node
import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const ROOT = path.resolve(__dirname, '..');
const HTML_PATH = path.join(ROOT, 'vocify_deck.html');
const LOGO_PATH = path.join(ROOT, 'logo.png');
const OUTPUT_PATH = path.join(ROOT, 'vocify_deck_final.pdf');

async function main() {
  const html = fs.readFileSync(HTML_PATH, 'utf8');
  const logoBase64 = fs.readFileSync(LOGO_PATH).toString('base64');
  const dataUri = 'data:image/png;base64,' + logoBase64;
  const htmlWithLogo = html.replace(/src="logo\.png"/g, `src="${dataUri}"`);

  const tempPath = path.join(ROOT, 'vocify_deck_temp.html');
  fs.writeFileSync(tempPath, htmlWithLogo);

  const browser = await puppeteer.launch({ headless: 'new' });
  const page = await browser.newPage();

  await page.setViewport({ width: 1920, height: 1080 });
  await page.goto('file://' + tempPath, { waitUntil: 'networkidle0', timeout: 30000 });

  await page.evaluateHandle('document.fonts.ready');
  await new Promise(r => setTimeout(r, 500));

  await page.pdf({
    path: OUTPUT_PATH,
    width: '1920px',
    height: '1080px',
    printBackground: true,
    margin: { top: 0, right: 0, bottom: 0, left: 0 },
  });

  await browser.close();
  fs.unlinkSync(tempPath);

  console.log('PDF generated:', OUTPUT_PATH);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
