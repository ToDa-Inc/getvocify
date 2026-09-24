import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  assistOverlayFields,
  dashboardOrigin,
  overlayBounds,
  overlayBoundsForState,
  overlayShellState,
  overlaySnippet,
  shouldQuitOnLastWindow,
  trayMenuTemplate,
  WINDOW_SIZE,
} from './shell.js';

describe('desktop shell', () => {
  it('pins the overlay to the bottom-right of the work area', () => {
    const bounds = overlayBounds({ workArea: { x: 0, y: 25, width: 1440, height: 875 } });
    assert.equal(bounds.width, 340);
    assert.equal(bounds.height, 64);
    assert.equal(bounds.x, 1076);
    assert.equal(bounds.y, 812);
  });

  it('widens the window for CRM review', () => {
    assert.ok(WINDOW_SIZE.review.width > WINDOW_SIZE.compact.width);
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
    assert.equal(overlaySnippet({ finalTranscript: '', interimTranscript: '' }, 'es'), 'Escuchando la reunión…');
    assert.equal(overlaySnippet({ finalTranscript: '', interimTranscript: '' }, 'en'), 'Listening to the meeting…');
  });

  it('forwards meeting assist to the overlay without inventing a card', () => {
    const overlay = overlayShellState({
      listening: true,
      lastLine: 'You: hello',
      kind: 'meeting',
      playbookReady: true,
      evidenceRefs: ['ev-1'],
      card: { text: 'Pregunta el precio' },
    });
    assert.equal(overlay.kind, 'meeting');
    assert.deepEqual(overlay.evidenceRefs, ['ev-1']);
    assert.equal(overlay.card.text, 'Pregunta el precio');
    assert.equal(overlay.lastLine, 'You: hello');
  });

  it('keeps call kind and empty evidence on the overlay', () => {
    const overlay = overlayShellState({
      listening: true,
      lastLine: 'Them: hi',
      kind: 'call',
      evidenceRefs: [],
    });
    assert.equal(overlay.kind, 'call');
    assert.deepEqual(overlay.evidenceRefs, []);
    assert.equal(overlay.card, undefined);
  });

  it('defaults missing evidence to an empty list for shell setState', () => {
    assert.deepEqual(assistOverlayFields({}).evidenceRefs, []);
    assert.deepEqual(assistOverlayFields({ kind: 'meeting' }).evidenceRefs, []);
  });

  it('forwards checklist progress to the overlay and grows bounds when visible', () => {
    const checklist = {
      observed: 1,
      applicable: 2,
      steps: [{ step_id: 's1', label: 'Saludo', status: 'met', evidence_refs: [] }],
    };
    const overlay = overlayShellState({
      listening: true,
      kind: 'meeting',
      checklist,
    });
    assert.deepEqual(overlay.checklist, checklist);
    const compact = overlayBoundsForState({ listening: true, kind: 'meeting' });
    const expanded = overlayBoundsForState({ listening: true, kind: 'meeting', checklist });
    assert.ok(expanded.height > compact.height);
  });
});
