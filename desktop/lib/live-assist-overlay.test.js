import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { liveAssistOverlayFromCopilotPayload } from './live-assist-overlay.js';

describe('live-assist-overlay', () => {
  it('fills overlay fields from a grounded suggest payload', () => {
    const overlay = liveAssistOverlayFromCopilotPayload(
      {
        playbook_ready: true,
        evidence_refs: ['ev-1'],
        text: 'Pregunta el precio',
      },
      { kind: 'meeting' },
    );
    assert.equal(overlay.kind, 'meeting');
    assert.equal(overlay.playbookReady, true);
    assert.deepEqual(overlay.evidenceRefs, ['ev-1']);
    assert.deepEqual(overlay.card, { text: 'Pregunta el precio' });
  });

  it('leaves card null when evidence_refs is empty', () => {
    const overlay = liveAssistOverlayFromCopilotPayload(
      {
        playbook_ready: true,
        evidence_refs: [],
        text: 'Should not appear',
      },
      { kind: 'call' },
    );
    assert.equal(overlay.kind, 'call');
    assert.deepEqual(overlay.evidenceRefs, []);
    assert.equal(overlay.card, null);
  });
});
