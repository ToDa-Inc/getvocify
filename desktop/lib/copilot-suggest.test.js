import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { createCopilotSuggestIngester } from './copilot-suggest.js';
import { liveAssistPayloadFromSuggestEvent } from './live-assist-overlay.js';

describe('copilot-suggest ingest', () => {
  it('maps a grounded result event into an overlay payload', () => {
    const payload = liveAssistPayloadFromSuggestEvent({
      type: 'result',
      playbook_ready: true,
      evidence_refs: ['ev-1'],
      suggestion: { say_this: 'Pregunta el precio' },
    });
    assert.deepEqual(payload, {
      playbook_ready: true,
      evidence_refs: ['ev-1'],
      text: 'Pregunta el precio',
    });
  });

  it('invokes onPayload when a result frame completes', () => {
    const payloads = [];
    const ingest = createCopilotSuggestIngester((payload) => payloads.push(payload));
    ingest.push('data: {"type":"result","playbook_ready":true,"evidence_refs":["ev-1"],"text":"Hi"}\n\n');
    assert.equal(payloads.length, 1);
    assert.equal(payloads[0].text, 'Hi');
  });
});
