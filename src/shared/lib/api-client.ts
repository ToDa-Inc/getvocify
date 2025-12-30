/**
 * API Client for Vocify backend
 * 
 * Single source of truth for all API calls.
 * Features:
 * - Automatic token injection
 * - Consistent error handling
 * - File upload support
 */

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1';

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
class ApiClient {
  private token: string | null = null;

  /**
   * Set the authentication token
   * Call this after login/signup or when restoring session
   */
  setToken(token: string | null): void {
    this.token = token;
  }

  /**
   * Get current token (for debugging/testing)
   */
  getToken(): string | null {
    return this.token;
  }

  /**
   * Clear the token (logout)
   */
  clearToken(): void {
    this.token = null;
  }

  /**
   * Core request method
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`;

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(this.token && { Authorization: `Bearer ${this.token}` }),
      ...options.headers,
    };

    const response = await fetch(url, { ...options, headers });

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
  delete<T>(endpoint: string): Promise<T> {
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
    fieldName = 'file'
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`;

    const formData = new FormData();
    formData.append(fieldName, file);

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        ...(this.token && { Authorization: `Bearer ${this.token}` }),
        // Note: Don't set Content-Type for FormData, browser sets it with boundary
      },
      body: formData,
    });

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
   * Upload file with progress tracking
   * 
   * Usage:
   * ```ts
   * const response = await api.uploadWithProgress<MemoResponse>(
   *   '/memos/upload',
   *   audioBlob,
   *   'audio',
   *   (progress) => setUploadProgress(progress)
   * );
   * ```
   */
  uploadWithProgress<T>(
    endpoint: string,
    file: Blob,
    fieldName = 'file',
    onProgress?: (progress: number) => void
  ): Promise<T> {
    return new Promise((resolve, reject) => {
      const url = `${API_BASE}${endpoint}`;

      const formData = new FormData();
      formData.append(fieldName, file);

      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable && onProgress) {
          const progress = Math.round((event.loaded / event.total) * 100);
          onProgress(progress);
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
            // Response wasn't JSON
          }
          reject(new ApiError(xhr.status, data));
        }
      });

      xhr.addEventListener('error', () => {
        reject(new ApiError(0, 'Network error'));
      });

      xhr.open('POST', url);
      if (this.token) {
        xhr.setRequestHeader('Authorization', `Bearer ${this.token}`);
      }
      xhr.send(formData);
    });
  }
}

// Export singleton instance
export const api = new ApiClient();


