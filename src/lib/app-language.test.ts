import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { resolveAppLanguage } from './app-language.ts';

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
