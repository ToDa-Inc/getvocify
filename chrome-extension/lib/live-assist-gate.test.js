import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { assistAllowed } from '../shared/ui/copilot/suggestion-state.js';
import { liveAssistGateFromSuggestPayload } from './live-assist-gate.js';

describe('liveAssistGateFromSuggestPayload', () => {
  it('maps playbook and evidence_refs into meeting card gate inputs', () => {
    const gate = liveAssistGateFromSuggestPayload({
      type: 'result',
      playbook_ready: true,
      evidence_refs: ['ev-1'],
      suggestion: { say_this: 'Pregunta el precio' },
    });
    assert.deepEqual(gate, { playbookReady: true, evidenceRefs: ['ev-1'] });
    assert.equal(
      assistAllowed({ kind: 'meeting', enabled: true, ...gate }).show,
      true,
    );
  });

  it('keeps the card silent when evidence refs are missing', () => {
    const gate = liveAssistGateFromSuggestPayload({
      type: 'result',
      playbook: true,
      suggestion: { say_this: 'Pregunta el precio' },
    });
    assert.deepEqual(gate, { playbookReady: true, evidenceRefs: [] });
    assert.equal(
      assistAllowed({ kind: 'meeting', enabled: true, ...gate }).show,
      false,
    );
  });

  it('does not show a phone call card even with grounding fields', () => {
    const gate = liveAssistGateFromSuggestPayload({
      type: 'result',
      grounded: true,
      evidence_refs: ['ev-1'],
    });
    assert.equal(
      assistAllowed({ kind: 'call', enabled: true, ...gate }).show,
      false,
    );
  });
});
