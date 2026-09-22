import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { memoMeetingChecklistView } from './memo-meeting-checklist.js';

const copy = { progressTemplate: '{met} of {applicable}', doneLabel: 'Done' };

describe('memoMeetingChecklistView', () => {
  it('hides when applicable is zero', () => {
    assert.equal(
      memoMeetingChecklistView(
        { applicable: 0, observed: 0, steps: [{ label: 'Intro', status: 'pending' }] },
        copy,
      ),
      null,
    );
  });

  it('includes the done label on met steps', () => {
    const view = memoMeetingChecklistView(
      {
        applicable: 1,
        observed: 1,
        steps: [{ label: 'Cierre', status: 'met' }],
      },
      { progressTemplate: '{met} de {applicable}', doneLabel: 'Hecho' },
    );
    assert.ok(view);
    assert.equal(view.steps[0].kind, 'met');
    assert.equal(view.steps[0].doneLabel, 'Hecho');
  });
});
