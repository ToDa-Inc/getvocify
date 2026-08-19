/**
 * Auth session helpers for the Chrome extension popup and API client.
 * Keep token storage in chrome.storage; these only decide which screen to show.
 */

export function isPublicAuthPath(endpoint) {
  const path = String(endpoint || '').split('?')[0];
  return path === '/auth/login' || path === '/auth/refresh';
}

function errorText(error) {
  const msg = String(error?.message || '');
  const detail = typeof error?.data?.detail === 'string' ? error.data.detail : '';
  return `${msg} ${detail}`;
}

/** HubSpot/Salesforce OAuth died — Vocify login is still valid. */
export function isCrmReconnectError(error) {
  if (!error) return false;
  const status = Number(error.status);
  if (status === 409) {
    return /hubspot|salesforce|reconnect/i.test(errorText(error));
  }
  return /hubspot authorization expired|reconnect hubspot|could not refresh hubspot|salesforce authorization expired|reconnect salesforce/i.test(
    errorText(error),
  );
}

export function isAuthFailure(error) {
  if (!error) return false;
  if (isCrmReconnectError(error)) return false;
  const status = Number(error.status);
  const text = errorText(error);
  if (status === 401) return true;
  return /session expired|unauthorized|missing authorization|not signed in|please sign in/i.test(text);
}

/** Only a 401 from /auth/refresh means the refresh token is dead. */
export function shouldClearAuthOnRefreshStatus(status) {
  return Number(status) === 401;
}

/** AUTH_REQUIRED / empty accessToken must not paint login while tokens remain. */
export function shouldEnterLoggedOut({ hasToken } = {}) {
  return !hasToken;
}

export function getTokenExpiryMs(token) {
  try {
    const payload = JSON.parse(atob(String(token || '').split('.')[1]));
    return payload?.exp ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

export function isAccessTokenFresh(token, nowMs = Date.now(), minTtlMs = 60_000) {
  const exp = getTokenExpiryMs(token);
  if (!exp) return false;
  return exp - nowMs > minTtlMs;
}

/** One in-flight refresh per JS context. Cross-context races also hit the server reuse cache. */
export function createRefreshGate(options) {
  let inflight = null;
  return () => {
    if (!inflight) {
      inflight = Promise.resolve()
        .then(() => {
          const current = options.getAccessToken();
          if (current && options.isFresh(current)) return current;
          return options.refresh();
        })
        .finally(() => {
          inflight = null;
        });
    }
    return inflight;
  };
}

/**
 * Popup must not paint record/idle/review while signed out or before init confirms a session.
 */
export function shouldPaintMainUi({ authStatus, stateAuthenticated } = {}) {
  if (authStatus !== 'signed_in') return false;
  if (stateAuthenticated === false) return false;
  return true;
}

/**
 * @returns {'login' | 'loading-error' | 'unknown'}
 */
export function screenForInitFailure(error, { hasToken } = {}) {
  if (!hasToken || isAuthFailure(error)) return 'login';
  const detail = typeof error?.data?.detail === 'string' ? error.data.detail : String(error?.message || '');
  const msg = String(error?.message || '');
  if (
    error?.status === 503 ||
    /oauth_client_id|supabase auth|token refresh failed|platform bug/i.test(detail)
  ) {
    return 'loading-error';
  }
  if (
    msg === 'Failed to fetch' ||
    (/network|connection|refused|load failed/i.test(msg) && !/oauth_client_id|platform bug/i.test(detail))
  ) {
    return 'loading-error';
  }
  return 'unknown';
}
