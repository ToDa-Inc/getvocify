/**
 * API Client for Vocify Backend
 *
 * Handles all HTTP requests with automatic token management and error handling.
 * Unpacked (Load unpacked) defaults to localhost:8888.
 * Packed / Chrome Web Store defaults to production.
 * chrome.storage.local.api_base always wins when set.
 */

import {
  createRefreshGate,
  isAccessTokenFresh,
  isCrmReconnectError,
  isPublicAuthPath,
  shouldClearAuthOnRefreshStatus,
} from './auth-session.js';
import { parseSseBuffer } from './copilot-sse.js';
import { PROD_API_BASE, isUnpackedExtension, resolveApiBase } from './api-base.js';

async function getApiBase() {
  try {
    const r = await chrome.storage.local.get(['api_base']);
    const unpacked = isUnpackedExtension(chrome.runtime?.getManifest?.() || {});
    return resolveApiBase({ unpacked, override: r.api_base });
  } catch {
    return PROD_API_BASE;
  }
}

/**
 * Custom error class for API errors
 */
export class ApiError extends Error {
  constructor(status, data, message) {
    super(message || `API Error: ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

/** Immediate view of tokens so clearTokens() wins over in-flight storage reads. */
let memoryTokens;

function rememberTokens(accessToken, refreshToken) {
  memoryTokens = {
    accessToken: accessToken || null,
    refreshToken: refreshToken || null,
  };
  return memoryTokens;
}

try {
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return;
    if (!changes.accessToken && !changes.refreshToken) return;
    const current = memoryTokens || { accessToken: null, refreshToken: null };
    rememberTokens(
      changes.accessToken ? changes.accessToken.newValue : current.accessToken,
      changes.refreshToken ? changes.refreshToken.newValue : current.refreshToken,
    );
  });
} catch { /* non-extension environments */ }

/**
 * Get stored authentication tokens
 */
async function getTokens() {
  if (memoryTokens?.accessToken) return memoryTokens;
  const result = await chrome.storage.local.get(['accessToken', 'refreshToken']);
  return rememberTokens(result.accessToken, result.refreshToken);
}

/**
 * Store authentication tokens
 */
async function setTokens(accessToken, refreshToken) {
  rememberTokens(accessToken, refreshToken);
  await chrome.storage.local.set({ accessToken, refreshToken });
}

/**
 * Clear stored tokens. Null the in-memory copy first so a concurrent
 * getTokens() cannot re-read a token that is about to be removed.
 */
async function clearTokens() {
  rememberTokens(null, null);
  await chrome.storage.local.remove(['accessToken', 'refreshToken']);
}

/**
 * Refresh access token. 401 clears the session; 503/429 keep stored tokens.
 */
async function doRefreshAccessToken() {
  const run = async () => {
    const { refreshToken, accessToken } = await getTokens();
    if (accessToken && isAccessTokenFresh(accessToken)) return accessToken;
    if (!refreshToken) throw new ApiError(401, null, 'No refresh token');

    const API_BASE = await getApiBase();
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        refresh_token: refreshToken,
        ...(accessToken ? { access_token: accessToken } : {}),
      }),
    });

    if (!response.ok) {
      if (shouldClearAuthOnRefreshStatus(response.status)) {
        await clearTokens();
      }
      let data = null;
      try { data = await response.json(); } catch { /* ignore */ }
      throw new ApiError(response.status, data, 'Token refresh failed');
    }

    const data = await response.json();
    await setTokens(data.access_token, data.refresh_token || refreshToken);
    return data.access_token;
  };

  if (globalThis.navigator?.locks?.request) {
    return navigator.locks.request('vocify-auth-refresh', run);
  }
  return run();
}

const refreshAccessToken = createRefreshGate({
  getAccessToken: () => memoryTokens?.accessToken || null,
  isFresh: isAccessTokenFresh,
  refresh: doRefreshAccessToken,
});

function shouldRefreshVocifySession(status, data) {
  if (status !== 401) return false;
  return !isCrmReconnectError({ status, data });
}

/**
 * Core request method with automatic token refresh
 */
async function request(endpoint, options = {}) {
  const API_BASE = await getApiBase();
  const url = `${API_BASE}${endpoint}`;
  const { accessToken } = await getTokens();

  if (!accessToken && !isPublicAuthPath(endpoint)) {
    throw new ApiError(
      401,
      { detail: 'Missing authorization header. Please sign in to get an access token.' },
      'Not signed in',
    );
  }

  const headers = {
    'Content-Type': 'application/json',
    ...(accessToken && { Authorization: `Bearer ${accessToken}` }),
    ...options.headers,
  };

  let response = await fetch(url, { ...options, headers });

  // Retry with a new Vocify JWT only when THIS request failed auth — not when
  // HubSpot/Salesforce OAuth needs a reconnect (those used to 401 and log us out).
  if (shouldRefreshVocifySession(response.status, null) && accessToken) {
    const preview = await response.clone().json().catch(() => ({}));
    if (shouldRefreshVocifySession(response.status, preview)) {
      try {
        const newToken = await refreshAccessToken();
        headers.Authorization = `Bearer ${newToken}`;
        response = await fetch(url, { ...options, headers });
      } catch (err) {
        if (shouldClearAuthOnRefreshStatus(err?.status)) {
          await clearTokens();
          throw new ApiError(401, null, 'Session expired');
        }
        throw err;
      }
    }
  }

  if (!response.ok) {
    let data = {};
    try { data = await response.json(); } catch {}
    throw new ApiError(response.status, data);
  }

  if (response.status === 204) return null;
  return response.json();
}

/**
 * API Client - Exported Methods
 */
export const api = {
  getApiBase,
  get API_BASE() { return PROD_API_BASE; },
  setTokens,
  clearTokens,
  getTokens,

  // Generic request method (for background.js)
  request,

  // Convenience methods
  get: (endpoint) => request(endpoint),
  post: (endpoint, body) => request(endpoint, { method: 'POST', body: JSON.stringify(body) }),

  // Auth
  async login(email, password) {
    const data = await request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    await setTokens(data.access_token, data.refresh_token);
    return data;
  },

  async getCurrentUser() {
    return request('/auth/me');
  },

  // Memos
  async uploadMemo(audioBlob, transcript = null) {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    if (transcript) formData.append('transcript', transcript);

    const { accessToken } = await getTokens();
    if (!accessToken) {
      throw new ApiError(
        401,
        { detail: 'Missing authorization header. Please sign in to get an access token.' },
        'Not signed in',
      );
    }
    const headers = { Authorization: `Bearer ${accessToken}` };

    const API_BASE = await getApiBase();
    let response = await fetch(`${API_BASE}/memos/upload`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (response.status === 401 && accessToken) {
      const preview = await response.clone().json().catch(() => ({}));
      if (shouldRefreshVocifySession(401, preview)) {
        try {
          const newToken = await refreshAccessToken();
          headers.Authorization = `Bearer ${newToken}`;
          response = await fetch(`${API_BASE}/memos/upload`, {
            method: 'POST',
            headers,
            body: formData,
          });
        } catch (err) {
          if (shouldClearAuthOnRefreshStatus(err?.status)) {
            await clearTokens();
            throw new ApiError(401, null, 'Session expired');
          }
          throw err;
        }
      }
    }

    if (!response.ok) throw new ApiError(response.status, null, 'Upload failed');
    return response.json();
  },

  async getMemo(memoId) {
    return request(`/memos/${memoId}`);
  },

  async uploadTranscript(transcript, sourceType = 'meeting_transcript') {
    return request('/memos/upload-transcript', {
      method: 'POST',
      body: JSON.stringify({ transcript: String(transcript).trim(), source_type: sourceType }),
    });
  },

  async reExtract(memoId) {
    return request(`/memos/${memoId}/re-extract`, { method: 'POST', body: '{}' });
  },

  /**
   * Stream POST /copilot/suggest (SSE). Same event shapes as the dashboard client.
   */
  async streamCopilotSuggest(body, onEvent, signal) {
    const API_BASE = await getApiBase();
    const { accessToken } = await getTokens();
    if (!accessToken) {
      onEvent({ type: 'error', message: 'Not signed in' });
      return;
    }
    const headers = {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${accessToken}`,
    };

    const doFetch = (authHeaders) => fetch(`${API_BASE}/copilot/suggest`, {
      method: 'POST',
      headers: authHeaders,
      body: JSON.stringify(body),
      signal,
    });

    let response = await doFetch(headers);
    if (response.status === 401 && accessToken) {
      const preview = await response.clone().json().catch(() => ({}));
      if (shouldRefreshVocifySession(401, preview)) {
        try {
          const newToken = await refreshAccessToken();
          headers.Authorization = `Bearer ${newToken}`;
          response = await doFetch(headers);
        } catch (err) {
          if (shouldClearAuthOnRefreshStatus(err?.status)) {
            await clearTokens();
            onEvent({ type: 'error', message: 'Session expired' });
            return;
          }
          onEvent({ type: 'error', message: err?.message || 'Could not refresh session' });
          return;
        }
      }
    }

    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
      try {
        const data = await response.json();
        const raw = data?.detail;
        if (typeof raw === 'string') detail = raw;
        else if (raw != null) detail = JSON.stringify(raw);
      } catch { /* ignore */ }
      onEvent({ type: 'error', message: detail });
      return;
    }

    if (!response.body) {
      onEvent({ type: 'error', message: 'No response body' });
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSseBuffer(buffer);
      buffer = parsed.rest;
      for (const event of parsed.events) onEvent(event);
    }
  },
};
