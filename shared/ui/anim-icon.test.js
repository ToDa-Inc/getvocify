import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { renderToString } from './html.js';
import { ANIM_ICONS, animIconAttrs, renderAnimIcon } from './components/anim-icon.js';

describe('anim icon', () => {
  it('draws each icon inside one sized, hidden-from-AT wrapper', () => {
    for (const name of ANIM_ICONS) {
      const out = renderToString(renderAnimIcon(name));
      assert.match(out, new RegExp(`class="v-ai v-ai--${name}"`));
      assert.match(out, /style="--v-ai-size:16px"/);
      assert.match(out, /aria-hidden="true"><svg class="v-ai__svg" viewBox="0 0 24 24"/);
    }
  });

  it('only accepts the held state that belongs to the icon', () => {
    assert.equal(animIconAttrs('refresh', { state: 'busy' }).className, 'v-ai v-ai--refresh is-busy');
    assert.equal(animIconAttrs('copy', { state: 'done' }).className, 'v-ai v-ai--copy is-done');
    assert.equal(animIconAttrs('phone', { state: 'ringing' }).className, 'v-ai v-ai--phone is-ringing');
    assert.equal(animIconAttrs('refresh', { state: 'ringing' }).className, 'v-ai v-ai--refresh');
    assert.equal(animIconAttrs('bell', { state: 'ring' }).className, 'v-ai v-ai--bell');
  });

  it('carries size and stroke as vars, clamping nonsense', () => {
    assert.equal(animIconAttrs('copy', { size: 14, stroke: 1.5 }).style, '--v-ai-size:14px;--v-ai-stroke:1.5');
    assert.equal(animIconAttrs('copy', { size: 'x', stroke: 'y' }).style, '--v-ai-size:16px');
    assert.equal(animIconAttrs('copy', { size: 2 }).style, '--v-ai-size:10px');
  });

  it('names itself when labelled, escapes the label, and renders nothing for an unknown icon', () => {
    assert.match(renderToString(renderAnimIcon('bell', { label: '"><b>' })), /role="img" aria-label="&quot;&gt;&lt;b&gt;"/);
    assert.equal(renderToString(renderAnimIcon('nope')), '');
  });

  it('copy carries the check it turns into; phone and bell keep the outline glyphs', () => {
    assert.match(renderToString(renderAnimIcon('copy')), /class="v-ai__check" pathLength="1"/);
    assert.match(renderToString(renderAnimIcon('phone')), /v-ai__wave--in[\s\S]*v-ai__wave--out/);
    assert.match(renderToString(renderAnimIcon('bell')), /class="v-ai__bell"[\s\S]*class="v-ai__clapper"/);
  });
});
