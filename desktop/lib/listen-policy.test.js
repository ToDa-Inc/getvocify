import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { applyTranscriptUpdate, canStartListen, startDeniedMessage } from './listen-policy.js';

describe('listen-policy', () => {
  it('requires login and refuses a second listen', () => {
    assert.equal(canStartListen({ hasToken: false }).ok, false);
    assert.equal(canStartListen({ hasToken: true, isListening: true }).reason, 'already_listening');
    assert.equal(canStartListen({ hasToken: true }).ok, true);
    assert.match(startDeniedMessage('no_system_audio'), /system audio/i);
    assert.match(startDeniedMessage('no_system_audio', { platform: 'linux' }), /PipeWire|PulseAudio/i);
  });

  it('tags prospect vs rep on the live transcript', () => {
    let state = { finalTranscript: '', interimTranscript: '' };
    state = applyTranscriptUpdate(state, {
      text: 'the price is too high',
      isFinal: true,
      audioChannel: 'prospect',
    });
    state = applyTranscriptUpdate(state, {
      text: 'we can start smaller',
      isFinal: true,
      audioChannel: 'rep',
    });
    assert.equal(state.finalTranscript, 'Them: the price is too high You: we can start smaller');
  });
});
