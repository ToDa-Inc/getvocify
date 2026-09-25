import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveUiLang, strings, uiLangInput } from './i18n.js';

test('notes rail and single-record-control keys exist in es and en', () => {
  const keys = [
    'desktopLoginLead',
    'desktopLoginAccent',
    'desktopLoginEmail',
    'desktopLoginPassword',
    'desktopLoginSubmit',
    'desktopReviewSummary',
    'desktopReviewNext',
    'desktopReviewCrm',
    'desktopReviewApprove',
    'desktopNewNote',
    'desktopOpenDashboard',
    'desktopLogout',
    'transcriptBackToLive',
    'desktopOpenSettings',
    'desktopNothingHeard',
    'desktopOffline',
    'desktopRetry',
    'desktopPrepareFailed',
    'desktopNoMeetingAudio',
  ];
  for (const key of keys) {
    assert.equal(typeof strings('es')[key], 'string', `es.${key}`);
    assert.equal(typeof strings('en')[key], 'string', `en.${key}`);
    assert.ok(strings('es')[key].length > 0, `es.${key} not empty`);
    assert.ok(strings('en')[key].length > 0, `en.${key} not empty`);
  }
});

test('uiLangInput forwards saved en/es and navigator for resolveUiLang', () => {
  assert.equal(resolveUiLang(uiLangInput('en', 'es-ES')), 'en');
  assert.equal(resolveUiLang(uiLangInput(null, 'en-GB')), 'en');
  assert.equal(resolveUiLang(uiLangInput(undefined, '')), 'es');
  assert.deepEqual(uiLangInput('fr', 'de-DE'), { navigatorLanguage: 'de-DE' });
});

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
