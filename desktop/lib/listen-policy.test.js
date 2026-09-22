import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  applyTranscriptUpdate,
  buildListenSession,
  canStartListen,
  contactIdForListenSession,
  startDeniedMessage,
} from './listen-policy.js';

describe('listen-policy', () => {
  it('copies contact record id onto listen session; deal pages stay ungrounded', () => {
    assert.equal(contactIdForListenSession({ objectType: 'contact', recordId: '42' }), '42');
    assert.equal(
      buildListenSession({ callMode: 'meeting', crmPageContext: { objectType: 'contact', recordId: '42' } })
        .contactId,
      '42',
    );
    assert.equal(contactIdForListenSession({ objectType: 'deal', recordId: '42' }), null);
    assert.equal(
      buildListenSession({ callMode: 'meeting', crmPageContext: { objectType: 'deal', recordId: '99' } })
        .contactId,
      null,
    );
    assert.equal(contactIdForListenSession(null), null);
  });

  it('requires login and refuses a second listen', () => {
    assert.equal(canStartListen({ hasToken: false }).ok, false);
    assert.equal(canStartListen({ hasToken: true, isListening: true }).reason, 'already_listening');
    assert.equal(canStartListen({ hasToken: true }).ok, true);
    assert.equal(
      canStartListen({
        hasToken: true,
        permissionGate: { ok: false, reason: 'no_system_audio' },
      }).reason,
      'no_system_audio',
    );
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
