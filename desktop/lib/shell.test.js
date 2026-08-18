import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  dashboardOrigin,
  overlayBounds,
  overlaySnippet,
  shouldQuitOnLastWindow,
  trayMenuTemplate,
} from './shell.js';

describe('desktop shell', () => {
  it('pins the overlay to the top-right of the work area', () => {
    const bounds = overlayBounds({ workArea: { x: 0, y: 25, width: 1440, height: 875 } });
    assert.equal(bounds.width, 380);
    assert.ok(bounds.x > 1000);
    assert.equal(bounds.y, 41);
  });

  it('shows Listen when idle and Stop when live', () => {
    const idle = trayMenuTemplate({ loggedIn: true, listening: false });
    assert.equal(idle.find((i) => i.id === 'listen').enabled, true);
    assert.equal(idle.find((i) => i.id === 'stop').enabled, false);
    const live = trayMenuTemplate({ loggedIn: true, listening: true });
    assert.equal(live.find((i) => i.id === 'listen').enabled, false);
    assert.equal(live.find((i) => i.id === 'stop').enabled, true);
  });

  it('keeps the Mac app alive in the tray when the last window closes', () => {
    assert.equal(shouldQuitOnLastWindow({ platform: 'darwin', isQuitting: false }), false);
    assert.equal(shouldQuitOnLastWindow({ platform: 'darwin', isQuitting: true }), true);
    assert.equal(shouldQuitOnLastWindow({ platform: 'linux', isQuitting: false }), true);
  });

  it('opens the Vocify dashboard, not the API host', () => {
    assert.equal(dashboardOrigin('https://api.getvocify.com/api/v1'), 'https://app.getvocify.com');
    assert.equal(dashboardOrigin('http://localhost:8888/api/v1'), 'http://localhost:8080');
  });

  it('uses the latest You/Them line for the overlay', () => {
    assert.equal(
      overlaySnippet({ finalTranscript: 'Them: price You: smaller', interimTranscript: '' }),
      'You: smaller',
    );
    assert.equal(
      overlaySnippet({ finalTranscript: 'Them: hi', interimTranscript: 'You: hello' }),
      'You: hello',
    );
    assert.equal(overlaySnippet({ finalTranscript: '', interimTranscript: '' }), 'Listening to the call…');
  });
});
