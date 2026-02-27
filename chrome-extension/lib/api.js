/**
 * API Client for Vocify Backend
 * 
 * Handles all HTTP requests with automatic token management and error handling.
 * API_BASE can be overridden via chrome.storage.local 'api_base' for production.
 */

const DEFAULT_API_BASE = 'http://localhost:8888/api/v1';

async function getApiBase() {
  try {
    const r = await chrome.storage.local.get(['api_base']);
    return r.api_base || DEFAULT_API_BASE;
  } catch {
    return DEFAULT_API_BASE;
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

/**
 * Get stored authentication tokens
 */
async function getTokens() {
  const result = await chrome.storage.local.get(['accessToken', 'refreshToken']);
  return {
    accessToken: result.accessToken || null,
    refreshToken: result.refreshToken || null,
  };
}

/**
 * Store authentication tokens
 */
async function setTokens(accessToken, refreshToken) {
  await chrome.storage.local.set({ accessToken, refreshToken });
}

/**
 * Clear stored tokens
 */
async function clearTokens() {
  await chrome.storage.local.remove(['accessToken', 'refreshToken']);
}

/**
 * Refresh access token
 */
async function refreshAccessToken() {
  const { refreshToken } = await getTokens();
  if (!refreshToken) throw new ApiError(401, null, 'No refresh token');

  const API_BASE = await getApiBase();
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) throw new ApiError(response.status, null, 'Token refresh failed');

  const data = await response.json();
  await setTokens(data.access_token, refreshToken);
  return data.access_token;
}

/**
 * Core request method with automatic token refresh
 */
async function request(endpoint, options = {}) {
  const API_BASE = await getApiBase();
  const url = `${API_BASE}${endpoint}`;
  const { accessToken } = await getTokens();

  const headers = {
    'Content-Type': 'application/json',
    ...(accessToken && { Authorization: `Bearer ${accessToken}` }),
    ...options.headers,
  };

  let response = await fetch(url, { ...options, headers });

  // Retry with refreshed token if 401
  if (response.status === 401 && accessToken) {
    try {
      const newToken = await refreshAccessToken();
      headers.Authorization = `Bearer ${newToken}`;
      response = await fetch(url, { ...options, headers });
    } catch {
      await clearTokens();
      throw new ApiError(401, null, 'Session expired');
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
  get API_BASE() { return DEFAULT_API_BASE; },
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
    const headers = accessToken ? { Authorization: `Bearer ${accessToken}` } : {};

    const API_BASE = await getApiBase();
    let response = await fetch(`${API_BASE}/memos/upload`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (response.status === 401 && accessToken) {
      const newToken = await refreshAccessToken();
      headers.Authorization = `Bearer ${newToken}`;
      response = await fetch(`${API_BASE}/memos/upload`, {
        method: 'POST',
        headers,
        body: formData,
      });
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
};
