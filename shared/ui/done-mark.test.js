import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { renderToString } from './html.js';
import { renderDoneMark } from './components/done-mark.js';

describe('done mark', () => {
  it('plays by default, draws a check, and names itself when labelled', () => {
    const out = renderToString(renderDoneMark({ label: 'Guardado en HubSpot' }));
    assert.match(out, /class="v-done is-playing"/);
    assert.match(out, /role="img" aria-label="Guardado en HubSpot"/);
    assert.match(out, /--v-done-size:64px/);
    assert.match(out, /d="M16\.5 26\.5 23 33l12\.5-13\.5"/);
    assert.doesNotMatch(out, /v-done--failed/);
  });

  it('rests without motion for a call saved earlier, and hides from AT when unlabelled', () => {
    const out = renderToString(renderDoneMark({ animate: false, size: 28 }));
    assert.match(out, /class="v-done"/);
    assert.doesNotMatch(out, /is-playing/);
    assert.match(out, /--v-done-size:28px/);
    assert.match(out, /aria-hidden="true"><span class="v-done__halo"/);
  });

  it('a failed write is an exclamation in the failure tone, never a check', () => {
    const out = renderToString(renderDoneMark({ tone: 'failed', label: 'No guardado' }));
    assert.match(out, /v-done--failed/);
    assert.match(out, /v-done__dot/);
    assert.doesNotMatch(out, /M16\.5 26\.5/);
  });

  it('clamps nonsense sizes and escapes the label', () => {
    assert.match(renderToString(renderDoneMark({ size: 'x' })), /--v-done-size:64px/);
    assert.match(renderToString(renderDoneMark({ size: 4 })), /--v-done-size:16px/);
    assert.match(renderToString(renderDoneMark({ label: '"><script>' })), /aria-label="&quot;&gt;&lt;script&gt;"/);
  });
});
