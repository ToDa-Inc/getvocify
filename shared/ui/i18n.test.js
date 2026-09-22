import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveUiLang, strings } from './i18n.js';

test('resolveUiLang prefers vocify_lang then navigatorLanguage then es fallback', () => {
  assert.equal(resolveUiLang({ vocify_lang: 'en-US', navigatorLanguage: 'es-ES' }), 'en');
  assert.equal(resolveUiLang({ navigatorLanguage: 'en-GB' }), 'en');
  assert.equal(resolveUiLang({ vocify_lang: 'fr', navigatorLanguage: 'de' }), 'es');
  assert.equal(resolveUiLang('en'), 'en');
});

test('listen chrome keys return es or en copy', () => {
  assert.equal(strings('es').listenIdleButton, 'Escuchar pestaña');
  assert.equal(strings('en').listenIdleButton, 'Listen to tab');
  assert.equal(strings('es').overlayListening, 'Escuchando la reunión…');
  assert.equal(strings('en').overlayListening, 'Listening to the meeting…');
  assert.equal(strings('en').checklistProgress(2, 5), '2 of 5');
  assert.equal(strings('es').listenHeaderTab('Acme'), 'Escuchando · Acme');
  assert.equal(strings('en').listenHeaderTab('Acme'), 'Listening · Acme');
  assert.equal(
    strings('es').memoHangUpFirst,
    'Cuelga la llamada antes de grabar una nota.',
  );
  assert.equal(
    strings('en').memoHangUpFirst,
    'Hang up the call before recording a memo.',
  );
  assert.equal(
    strings('es').memoStopListeningFirst,
    'Deja de escuchar la pestaña antes de grabar una nota.',
  );
  assert.equal(
    strings('en').memoStopListeningFirst,
    'Stop listening to the tab before recording a memo.',
  );
});
