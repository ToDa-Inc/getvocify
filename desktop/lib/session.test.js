import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { isSessionError, startScreen } from './session.js';

describe('session', () => {
  it('treats 401 and expired-session details as a lost session', () => {
    assert.equal(isSessionError({ status: 401 }), true);
    assert.equal(isSessionError({ status: 400, detail: 'Invalid or expired session' }), true);
    assert.equal(isSessionError({ status: 500, detail: 'boom' }), false);
  });
  it('shows login unless a stored token passes /auth/me', () => {
    assert.equal(startScreen({ hasToken: false, meOk: false }), 'login');
    assert.equal(startScreen({ hasToken: true, meOk: false }), 'login');
    assert.equal(startScreen({ hasToken: true, meOk: true }), 'listen');
  });
});
