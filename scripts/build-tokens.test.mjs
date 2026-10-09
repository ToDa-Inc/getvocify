import test from 'node:test';
import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildAll, renderTarget } from './build-tokens.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const tokens = JSON.parse(readFileSync(resolve(here, '../shared/tokens/tokens.json'), 'utf8'));

function sandbox({ withDesktop }) {
  const root = mkdtempSync(join(tmpdir(), 'tokens-'));
  cpSync(resolve(here, '../shared/tokens'), join(root, 'shared/tokens'), { recursive: true });
  if (withDesktop) mkdirSync(join(root, 'desktop/renderer'), { recursive: true });
  return root;
}

test('web gets triplets under canonical names (Tailwind consumes hsl(var(--x)))', () => {
  const css = renderTarget(tokens, tokens.targets.web);
  assert.match(css, /--muted-foreground: 30 6% 42%;/);
  assert.match(css, /--muted: 38 20% 90%;/);
  assert.match(css, /--radius-pill: 999px;/);
});

test('extension keeps its own names and full colors, so styles.css needs no rewrite', () => {
  const css = renderTarget(tokens, tokens.targets.extension);
  assert.match(css, /--muted: hsl\(30 6% 42%\);/, 'extension --muted is text color, not the web surface');
  assert.match(css, /--secondary: hsl\(38 25% 88%\);/);
  assert.doesNotMatch(css, /  --muted-foreground:/);
});

test('every surface gets the same --v-* namespace for the shared kit', () => {
  for (const key of ['web', 'desktop', 'extension']) {
    const css = renderTarget(tokens, tokens.targets[key]);
    assert.match(css, /--v-beige: hsl\(35 25% 35%\);/, key);
    assert.match(css, /--v-muted-foreground: hsl\(30 6% 42%\);/, key);
    assert.match(css, /--v-radius-container: 18px;/, key);
  }
});

test('unknown token in a target name map fails loudly', () => {
  assert.throws(() => renderTarget(tokens, { format: 'color', names: { x: 'nope' } }), /Unknown color token "nope"/);
});

test('build writes present targets, skips an absent optional desktop, and --check passes after', () => {
  const root = sandbox({ withDesktop: false });
  const first = buildAll({ root, env: {} });
  assert.deepEqual(first.written.sort(), ['extension', 'web']);
  assert.deepEqual(first.skipped, ['desktop']);
  assert.deepEqual(buildAll({ root, check: true, env: {} }).stale, []);
});

test('--check flags a hand-edited generated file', () => {
  const root = sandbox({ withDesktop: true });
  buildAll({ root, env: {} });
  writeFileSync(join(root, 'src/styles/tokens.css'), '/* edited */');
  assert.deepEqual(buildAll({ root, check: true, env: {} }).stale, ['web']);
});

test('VOCIFY_DESKTOP_DIR points the desktop output at a sibling repo', () => {
  const root = sandbox({ withDesktop: false });
  const sibling = mkdtempSync(join(tmpdir(), 'desktop-'));
  mkdirSync(join(sibling, 'renderer'), { recursive: true });
  const report = buildAll({ root, env: { VOCIFY_DESKTOP_DIR: sibling } });
  assert.ok(report.written.includes('desktop'));
  assert.match(readFileSync(join(sibling, 'renderer/tokens.css'), 'utf8'), /--beige: 35 25% 35%;/);
});
