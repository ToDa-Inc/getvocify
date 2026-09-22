import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildCopilotSuggestRequestBody,
  copilotSuggestCallMode,
  createCopilotSuggestIngester,
  markCopilotSuggestRequested,
  resetCopilotSuggestRequestDedupe,
  shouldFetchCopilotSuggest,
  shouldRequestCopilotSuggest,
} from './copilot-suggest.js';
import { liveAssistPayloadFromSuggestEvent } from './live-assist-overlay.js';

describe('buildCopilotSuggestRequestBody', () => {
  it('maps session callMode via liveAssistKind; contact_id only when session has one', () => {
    assert.equal(copilotSuggestCallMode({ callMode: 'meeting' }), 'meeting');
    assert.equal(copilotSuggestCallMode({ callMode: 'call' }), 'speakerphone');
    assert.equal(copilotSuggestCallMode({}), 'speakerphone');

    const bare = buildCopilotSuggestRequestBody({
      session: { callMode: 'meeting' },
      transcriptWindow: 'They: hello',
      latestTurn: 'hello',
    });
    assert.equal(bare.call_mode, 'meeting');
    assert.equal(bare.latest_turn, 'hello');
    assert.equal('contact_id' in bare, false);

    const call = buildCopilotSuggestRequestBody({
      session: { callMode: 'call' },
      transcriptWindow: 'x',
      latestTurn: 'y',
    });
    assert.equal(call.call_mode, 'speakerphone');

    const grounded = buildCopilotSuggestRequestBody({
      session: { callMode: 'meeting', contactId: 'hs-99' },
      transcriptWindow: 'x',
      latestTurn: 'y',
    });
    assert.equal(grounded.contact_id, 'hs-99');
  });
});

describe('shouldFetchCopilotSuggest', () => {
  it('skips empty lines and duplicate final lines; fetches when the line changes', () => {
    assert.equal(shouldFetchCopilotSuggest('', ''), false);
    assert.equal(shouldFetchCopilotSuggest('', '   '), false);
    assert.equal(shouldFetchCopilotSuggest('hola', 'hola'), false);
    assert.equal(shouldFetchCopilotSuggest('hola', '  hola  '), false);
    assert.equal(shouldFetchCopilotSuggest('', 'nueva línea'), true);
    assert.equal(shouldFetchCopilotSuggest('antes', 'después'), true);
  });

  it('dedupes only after a successful mark; failed lines stay eligible', () => {
    resetCopilotSuggestRequestDedupe();
    assert.equal(shouldRequestCopilotSuggest('hola'), true);
    assert.equal(shouldRequestCopilotSuggest('hola'), true);
    markCopilotSuggestRequested('hola');
    assert.equal(shouldRequestCopilotSuggest('hola'), false);
    assert.equal(shouldRequestCopilotSuggest('otra'), true);
    resetCopilotSuggestRequestDedupe();
    assert.equal(shouldRequestCopilotSuggest('hola'), true);
  });
});

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
