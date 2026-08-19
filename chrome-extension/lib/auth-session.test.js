import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  createRefreshGate,
  isAuthFailure,
  isCrmReconnectError,
  isPublicAuthPath,
  screenForInitFailure,
  shouldClearAuthOnRefreshStatus,
  shouldEnterLoggedOut,
  shouldPaintMainUi,
} from './auth-session.js';

describe('isPublicAuthPath', () => {
  it('allows login and refresh without a stored token', () => {
    assert.equal(isPublicAuthPath('/auth/login'), true);
    assert.equal(isPublicAuthPath('/auth/refresh'), true);
  });

  it('requires a token for session and CRM calls', () => {
    assert.equal(isPublicAuthPath('/auth/me'), false);
    assert.equal(isPublicAuthPath('/memos?limit=5'), false);
  });
});

describe('isAuthFailure', () => {
  it('treats 401 and missing-authorization as signed out', () => {
    assert.equal(isAuthFailure({ status: 401, message: 'API Error: 401' }), true);
    assert.equal(isAuthFailure({
      status: 401,
      data: { detail: 'Missing authorization header. Please sign in to get an access token.' },
    }), true);
    assert.equal(isAuthFailure({ message: 'Not signed in', data: { detail: 'Missing authorization header' } }), true);
  });

  it('does not treat network or render errors as logout', () => {
    assert.equal(isAuthFailure({ message: 'Failed to fetch' }), false);
    assert.equal(isAuthFailure({ status: 500, message: 'Server error' }), false);
  });

  it('does not treat HubSpot reconnect as a Vocify logout', () => {
    const hubspot401 = {
      status: 401,
      data: {
        detail: "HubSpot authorization expired. Please reconnect HubSpot. (Client error '400 Bad Request' for url 'https://api.hubapi.com/oauth/v1/token')",
      },
    };
    assert.equal(isCrmReconnectError(hubspot401), true);
    assert.equal(isAuthFailure(hubspot401), false);
    assert.equal(screenForInitFailure(hubspot401, { hasToken: true }), 'unknown');
  });

  it('does not treat HubSpot 409 as a Vocify logout', () => {
    const hubspot409 = {
      status: 409,
      data: { detail: 'HubSpot authorization expired. Please reconnect HubSpot.' },
    };
    assert.equal(isCrmReconnectError(hubspot409), true);
    assert.equal(isAuthFailure(hubspot409), false);
  });
});

describe('shouldPaintMainUi', () => {
  it('never paints idle/record before login is confirmed', () => {
    assert.equal(shouldPaintMainUi({ authStatus: 'unknown' }), false);
    assert.equal(shouldPaintMainUi({ authStatus: 'signed_out' }), false);
    assert.equal(shouldPaintMainUi({
      authStatus: 'signed_out',
      stateAuthenticated: undefined,
    }), false);
  });

  it('ignores GET_STATE / STATE_UPDATED when the background reports no token', () => {
    assert.equal(shouldPaintMainUi({
      authStatus: 'signed_in',
      stateAuthenticated: false,
    }), false);
  });

  it('paints the main UI only when the popup session is signed in', () => {
    assert.equal(shouldPaintMainUi({ authStatus: 'signed_in' }), true);
    assert.equal(shouldPaintMainUi({
      authStatus: 'signed_in',
      stateAuthenticated: true,
    }), true);
  });
});

describe('screenForInitFailure', () => {
  it('shows login when tokens are missing or the API rejects auth', () => {
    assert.equal(screenForInitFailure({ message: 'whatever' }, { hasToken: false }), 'login');
    assert.equal(screenForInitFailure({
      status: 401,
      data: { detail: 'Missing authorization header. Please sign in to get an access token.' },
    }, { hasToken: true }), 'login');
  });

  it('does not send auth failures to the idle record screen', () => {
    assert.notEqual(screenForInitFailure({ status: 401 }, { hasToken: true }), 'unknown');
  });

  it('keeps network failures on the loading-error screen', () => {
    assert.equal(screenForInitFailure({ message: 'Failed to fetch' }, { hasToken: true }), 'loading-error');
  });

  it('keeps a stored session on Auth outage instead of showing login', () => {
    assert.equal(screenForInitFailure({
      status: 503,
      data: { detail: 'Auth service temporarily unreachable. Please try again.' },
    }, { hasToken: true }), 'loading-error');
  });
});

describe('shouldClearAuthOnRefreshStatus', () => {
  it('clears stored tokens only on a real 401', () => {
    assert.equal(shouldClearAuthOnRefreshStatus(401), true);
    assert.equal(shouldClearAuthOnRefreshStatus(503), false);
    assert.equal(shouldClearAuthOnRefreshStatus(429), false);
    assert.equal(shouldClearAuthOnRefreshStatus(500), false);
  });
});

describe('shouldEnterLoggedOut', () => {
  it('does not paint login while a token is still stored', () => {
    assert.equal(shouldEnterLoggedOut({ hasToken: false }), true);
    assert.equal(shouldEnterLoggedOut({ hasToken: true }), false);
  });
});

describe('createRefreshGate', () => {
  it('shares one refresh across overlapping callers', async () => {
    let calls = 0;
    const gate = createRefreshGate({
      getAccessToken: () => null,
      isFresh: () => false,
      refresh: async () => {
        calls += 1;
        await new Promise((r) => setTimeout(r, 20));
        return 'new-token';
      },
    });
    const [a, b] = await Promise.all([gate(), gate()]);
    assert.equal(a, 'new-token');
    assert.equal(b, 'new-token');
    assert.equal(calls, 1);
  });
});
