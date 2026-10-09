import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { initialPillState, pillDecision } from '../shared/ui/copilot/pill.js';

describe('copilot pill card (extension popup)', () => {
  it('holds through 3s, withdraws at 10s, and cooldowns the same category at 15s', () => {
    let pillState = initialPillState();
    const baseInput = {
      kind: 'meeting',
      enabled: true,
      speakerRole: 'prospect',
      text: 'Pregunta por el presupuesto del trimestre',
      category: 'price',
      meetingId: 'listen-1',
    };

    let at0 = pillDecision(pillState, baseInput, 0);
    assert.equal(at0.show, true);
    assert.ok(at0.text);
    pillState = at0.state;

    let at3 = pillDecision(pillState, baseInput, 3000);
    assert.equal(at3.show, true);
    pillState = at3.state;

    let at10 = pillDecision(pillState, baseInput, 10000);
    assert.equal(at10.show, false);
    pillState = at10.state;

    let at15 = pillDecision(
      pillState,
      { ...baseInput, text: 'Otra línea sobre precio' },
      15000,
    );
    assert.equal(at15.show, false);
  });
});
