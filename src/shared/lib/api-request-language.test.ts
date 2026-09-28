import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  acceptLanguageRequestHeader,
  resetApiRequestLanguage,
  setApiRequestLanguage,
} from './api-request-language.ts';

describe('acceptLanguageRequestHeader', () => {
  beforeEach(() => {
    resetApiRequestLanguage();
  });

  it('is unset until the app language is registered', () => {
    assert.deepEqual(acceptLanguageRequestHeader(), {});
  });

  it('sends en or es when set', () => {
    setApiRequestLanguage('en');
    assert.deepEqual(acceptLanguageRequestHeader(), { 'Accept-Language': 'en' });

    setApiRequestLanguage('es');
    assert.deepEqual(acceptLanguageRequestHeader(), { 'Accept-Language': 'es' });
  });

  it('clears the header when language is reset', () => {
    setApiRequestLanguage('en');
    setApiRequestLanguage(null);
    assert.deepEqual(acceptLanguageRequestHeader(), {});
  });
});
