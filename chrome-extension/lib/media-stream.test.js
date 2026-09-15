import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  cloneAudioTracks,
  isUsableMicRecording,
} from './media-stream.js';

describe('cloneAudioTracks', () => {
  it('clones each audio track so MediaRecorder and live STT do not share one', () => {
    const original = {
      id: 'orig',
      clone() {
        return { id: 'clone' };
      },
    };
    const cloned = cloneAudioTracks({ getAudioTracks: () => [original] });
    assert.deepEqual(cloned, [{ id: 'clone' }]);
  });
});

describe('isUsableMicRecording', () => {
  it('rejects recordings shorter than the dashboard 5s floor', () => {
    const result = isUsableMicRecording({ durationMs: 1500, byteLength: 26449 });
    assert.equal(result.ok, false);
    assert.equal(result.reason, 'too_short');
  });

  it('rejects tiny blobs that STT will call corrupt', () => {
    const result = isUsableMicRecording({ durationMs: 10600, byteLength: 400 });
    assert.equal(result.ok, false);
    assert.equal(result.reason, 'invalid_audio');
  });

  it('accepts a normal memo-length webm', () => {
    const result = isUsableMicRecording({ durationMs: 22000, byteLength: 180000 });
    assert.equal(result.ok, true);
  });
});
