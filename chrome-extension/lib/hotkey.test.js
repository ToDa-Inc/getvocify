import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { actionsForCommand } from './hotkey.js';

describe('actionsForCommand', () => {
  it('opens the panel and does not start recording', () => {
    assert.deepEqual(actionsForCommand('toggle-recording'), {
      openUi: true,
      toggleRecording: false,
    });
  });

  it('ignores unknown commands', () => {
    assert.deepEqual(actionsForCommand('something-else'), {
      openUi: false,
      toggleRecording: false,
    });
  });
});
