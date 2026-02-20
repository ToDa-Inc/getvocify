/**
 * API Client for Vocify backend
 * 
 * Single source of truth for all API calls.
 * Features:
 * - Automatic token injection
 * - Consistent error handling
 * - File upload support
 */

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8888/api/v1';
const REFRESH_KEY = 'vocify_refresh';
/**
 * Custom error class for API errors
 * Provides structured access to error details
 */
export class ApiError extends Error {
  constructor(
    public status: number,
    public data: unknown,
    message?: string
  ) {
    super(message ?? `API Error: ${status}`);
    this.name = 'ApiError';
  }

  /** Check if error is a validation error (400) */
  get isValidation(): boolean {
    return this.status === 400;
  }

  /** Check if error is unauthorized (401) */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** Check if error is forbidden (403) */
  get isForbidden(): boolean {
    return this.status === 403;
  }

  /** Check if error is not found (404) */
  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** Check if error is a server error (5xx) */
  get isServerError(): boolean {
    return this.status >= 500;
  }
}

/**
 * API Client singleton
 * 
 * Usage:
 * ```ts
 * import { api } from '@/shared/lib/api-client';
 * 
 * // Set token after login
 * api.setToken(accessToken);
 * 
 * // Make requests
 * const memos = await api.get<Memo[]>('/memos');
 * const memo = await api.post<Memo>('/memos', { data });
 * ```
 */
type OnAuthClearedCallback = () => void;

class ApiClient {
  private onAuthCleared: OnAuthClearedCallback | null = null;

  /**
   * Register callback when auth is cleared (e.g. after failed refresh).
   * Use to invalidate auth state in React Query, etc.
   */
  setOnAuthCleared(cb: OnAuthClearedCallback | null): void {
    this.onAuthCleared = cb;
  }

  /**
   * Helper to get token with direct localStorage access
   * This is the "Senior" way to ensure we never have an out-of-sync singleton state
   */
  private getAuthToken(): string | null {
    const stored = localStorage.getItem('vocify_token');
    
    // Guard against literal 'undefined' string which causes 500 errors in backend
    if (!stored || stored === 'undefined' || stored === 'null') {
      return null;
    }
    
    return stored;
  }

  /**
   * Set the authentication token
   * We still keep this for manual overrides, but preference is localStorage
   */
  setToken(token: string | null): void {
    if (token) {
      localStorage.setItem('vocify_token', token);
    } else {
      localStorage.removeItem('vocify_token');
    }
  }

  /**
   * Get current token (for debugging/testing)
   */
  getToken(): string | null {
    return this.getAuthToken();
  }

  /**
   * Clear the token (logout)
   */
  clearToken(): void {
    localStorage.removeItem('vocify_token');
  }

  /**
   * Clear all auth state (token + refresh token). Call when refresh fails.
   */
  clearAllAuth(): void {
    localStorage.removeItem('vocify_token');
    localStorage.removeItem(REFRESH_KEY);
    this.onAuthCleared?.();
  }

  /**
   * Try to refresh the access token. Returns new token or null on failure.
   */
  private async tryRefreshToken(): Promise<string | null> {
    const refreshToken = localStorage.getItem(REFRESH_KEY);
    if (!refreshToken || refreshToken === 'undefined' || refreshToken === 'null') {
      return null;
    }
    try {
      const url = `${API_BASE}/auth/refresh`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return null;
      const data = (await res.json()) as { access_token?: string; refresh_token?: string };
      const accessToken = data.access_token;
      if (accessToken) {
        this.setToken(accessToken);
        if (data.refresh_token) {
          localStorage.setItem(REFRESH_KEY, data.refresh_token);
        }
        return accessToken;
      }
      return null;
    } catch {
      return null;
    }
  }

  /**
   * Core request method. On 401, attempts token refresh and retries once.
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    isRetry = false
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`;
    const token = this.getAuthToken();

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    };

    const response = await fetch(url, { ...options, headers });

    // On 401: try refresh and retry once (skip for auth endpoints and retries)
    if (response.status === 401 && !isRetry && !endpoint.startsWith('/auth/')) {
      const newToken = await this.tryRefreshToken();
      if (newToken) {
        return this.request<T>(endpoint, {
          ...options,
          headers: {
            ...options.headers,
            'Content-Type': 'application/json',
            Authorization: `Bearer ${newToken}`,
          },
        }, true);
      }
      this.clearAllAuth();
    }

    // Handle errors
    if (!response.ok) {
      let data: unknown = {};
      try {
        data = await response.json();
      } catch {
        // Response body wasn't JSON
      }
      throw new ApiError(response.status, data);
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  /**
   * GET request
   */
  get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  /**
   * POST request with JSON body
   */
  post<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  /**
   * PUT request with JSON body
   */
  put<T>(endpoint: string, data: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  /**
   * PATCH request with JSON body
   */
  patch<T>(endpoint: string, data: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  /**
   * DELETE request
   */
  delete<T = void>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }

  /**
   * Upload file (multipart/form-data)
   * 
   * Usage:
   * ```ts
   * const response = await api.upload<MemoResponse>('/memos/upload', audioBlob, 'audio');
   * ```
   */
  async upload<T>(
    endpoint: string,
    file: Blob,
    fieldName = 'file',
    isRetry = false
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`;
    const token = this.getAuthToken();

    const formData = new FormData();
    formData.append(fieldName, file);

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        ...(token && { Authorization: `Bearer ${token}` }),
        // Note: Don't set Content-Type for FormData, browser sets it with boundary
      },
      body: formData,
    });

    if (response.status === 401 && !isRetry && !endpoint.startsWith('/auth/')) {
      const newToken = await this.tryRefreshToken();
      if (newToken) {
        return this.upload<T>(endpoint, file, fieldName, true);
      }
      this.clearAllAuth();
    }

    if (!response.ok) {
      let data: unknown = {};
      try {
        data = await response.json();
      } catch {
        // Response body wasn't JSON
      }
      throw new ApiError(response.status, data);
    }

    return response.json();
  }

  /**
   * Upload file with progress tracking.
   * On 401, attempts token refresh and retries once.
   */
  async uploadWithProgress<T>(
    endpoint: string,
    file: Blob,
    fieldName = 'file',
    onProgress?: (progress: number) => void,
    additionalFields?: Record<string, string>,
    isRetry = false
  ): Promise<T> {
    const doUpload = (): Promise<T> =>
      new Promise((resolve, reject) => {
        const url = `${API_BASE}${endpoint}`;
        const formData = new FormData();
        formData.append(fieldName, file);
        if (additionalFields) {
          Object.entries(additionalFields).forEach(([key, value]) => {
            if (value) formData.append(key, value);
          });
        }

        const xhr = new XMLHttpRequest();
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable && onProgress) {
            onProgress(Math.round((event.loaded / event.total) * 100));
          }
        });

        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText));
            } catch {
              reject(new ApiError(xhr.status, 'Invalid JSON response'));
            }
          } else {
            let data: unknown = {};
            try {
              data = JSON.parse(xhr.responseText);
            } catch {
              // ignore
            }
            reject(new ApiError(xhr.status, data));
          }
        });

        xhr.addEventListener('error', () => reject(new ApiError(0, 'Network error')));

        xhr.open('POST', url);
        const token = this.getAuthToken();
        if (token) {
          xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        }
        xhr.send(formData);
      });

    try {
      return await doUpload();
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 401 &&
        !isRetry &&
        !endpoint.startsWith('/auth/')
      ) {
        const newToken = await this.tryRefreshToken();
        if (newToken) {
          return this.uploadWithProgress<T>(
            endpoint,
            file,
            fieldName,
            onProgress,
            additionalFields,
            true
          );
        }
        this.clearAllAuth();
      }
      throw err;
    }
  }
}

// Export singleton instance
export const api = new ApiClient();


