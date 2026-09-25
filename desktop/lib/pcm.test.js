import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { downsampleTo16k, floatTo16BitPcm } from './pcm.js';

describe('pcm', () => {
  it('converts peaks to signed 16-bit', () => {
    const buf = floatTo16BitPcm(new Float32Array([1, -1, 0]));
    const view = new Int16Array(buf);
    assert.equal(view[0], 0x7fff);
    assert.equal(view[1], -0x8000);
    assert.equal(view[2], 0);
  });

  it('downsamples 48k to 16k by keeping every third sample', () => {
    const input = new Float32Array([1, 2, 3, 4, 5, 6]);
    const out = downsampleTo16k(input, 48000);
    assert.equal(out.length, 2);
    assert.equal(out[0], 1);
    assert.equal(out[1], 4);
  });
});
