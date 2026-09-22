import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  copilotAssistToggleLabel,
  isMeetingListenActive,
  shouldShowCopilotChecklist,
} from './copilot-meeting-ui.js';

describe('copilot meeting popup chrome', () => {
  it('detects meeting listen and assist labels', () => {
    assert.equal(
      isMeetingListenActive({ callMode: 'meeting', isCopilotListening: true }),
      true,
    );
    assert.equal(isMeetingListenActive({ callMode: 'call', isCopilotListening: true }), false);
    assert.equal(copilotAssistToggleLabel(false, 'es'), 'Ayuda');
    assert.equal(copilotAssistToggleLabel(true, 'es'), 'Ocultar ayuda');
    assert.equal(copilotAssistToggleLabel(false, 'en'), 'Help');
    assert.equal(copilotAssistToggleLabel(true, 'en'), 'Hide help');
  });

  it('hides checklist when applicable is zero', () => {
    const live = { callMode: 'meeting', listenPhase: 'live' };
    assert.equal(shouldShowCopilotChecklist(live, { applicable: 0, steps: [] }), false);
    assert.equal(
      shouldShowCopilotChecklist(live, { applicable: 2, steps: [{ label: 'x', status: 'pending' }] }),
      true,
    );
  });
});
