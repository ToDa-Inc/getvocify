import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { assertArtifactComplete, assertInternalDmg } from './package-gate.js';

const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
const workflow = readFileSync(new URL('../../.github/workflows/desktop-dmg.yml', import.meta.url), 'utf8');

test('an unsigned package is not published as a signed distribution', () => {
  assert.equal(assertInternalDmg(pkg).publishAsSigned, false);
  assert.equal(pkg.build.mac.identity, null);
  assert.equal(pkg.build.mac.hardenedRuntime, false);
  assert.match(workflow, /CSC_IDENTITY_AUTO_DISCOVERY: "false"/);
  assert.doesNotMatch(workflow, /Developer ID Application/);
});

test('the DMG layout puts Vocify on the left and Applications on the right', () => {
  const layout = assertInternalDmg(pkg);
  assert.ok(layout.app.x < layout.applications.x);
  assert.equal(layout.applications.path, '/Applications');
  assert.match(pkg.build.dmg.background, /dmg-background\.png$/);
});

test('an artifact without the helper or shared kit fails even if the builder exited 0', () => {
  assert.throws(
    () => assertArtifactComplete(['Vocify Companion.app/Contents/MacOS/Vocify Companion']),
    /helper|shared/,
  );
  assert.doesNotThrow(() =>
    assertArtifactComplete([
      'Vocify Companion.app/Contents/Resources/vocify-tap',
      'Vocify Companion.app/Contents/Resources/app/renderer/shared/ui/transcript.js',
    ]),
  );
});
