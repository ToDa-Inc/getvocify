import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  appLanguageToPersistFromVisit,
  htmlLang,
  resolveAppLanguage,
} from './app-language.ts';

describe('htmlLang', () => {
  it('EN maps to en', () => {
    assert.equal(htmlLang('EN'), 'en');
  });

  it('ES maps to es', () => {
    assert.equal(htmlLang('ES'), 'es');
  });
});

describe('resolveAppLanguage', () => {
  it('stored en on /dashboard is EN', () => {
    assert.equal(resolveAppLanguage({ stored: 'en', path: '/dashboard' }), 'EN');
  });

  it('no stored value on /dashboard is ES', () => {
    assert.equal(resolveAppLanguage({ stored: null, path: '/dashboard' }), 'ES');
  });

  it('no stored value on /en is EN', () => {
    assert.equal(resolveAppLanguage({ stored: null, path: '/en' }), 'EN');
  });

  it('stored es on /en is ES', () => {
    assert.equal(resolveAppLanguage({ stored: 'es', path: '/en' }), 'ES');
  });
});

describe('appLanguageToPersistFromVisit', () => {
  it('path /en and stored null persists EN', () => {
    assert.equal(appLanguageToPersistFromVisit({ stored: null, path: '/en' }), 'EN');
  });

  it('path /dashboard and stored null does not persist', () => {
    assert.equal(appLanguageToPersistFromVisit({ stored: null, path: '/dashboard' }), null);
  });
});
