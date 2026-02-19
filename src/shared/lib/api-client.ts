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
   * Core request method
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`;
    const token = this.getAuthToken();

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
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
    fieldName = 'file'
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
   *   (progress) => setUploadProgress(progress),
   *   { transcript: 'pre-transcribed text' }
   * );
   * ```
   */
  uploadWithProgress<T>(
    endpoint: string,
    file: Blob,
    fieldName = 'file',
    onProgress?: (progress: number) => void,
    additionalFields?: Record<string, string>
  ): Promise<T> {
    return new Promise((resolve, reject) => {
      const url = `${API_BASE}${endpoint}`;

      const formData = new FormData();
      formData.append(fieldName, file);
      
      // Add additional form fields (e.g., transcript)
      if (additionalFields) {
        Object.entries(additionalFields).forEach(([key, value]) => {
          if (value) {
            formData.append(key, value);
          }
        });
      }

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
      
      const token = this.getAuthToken();
      console.log('API Client: Uploading with token:', token ? `${token.substring(0, 8)}...` : 'MISSING');
      
      if (token) {
        xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      }
      xhr.send(formData);
    });
  }
}

// Export singleton instance
export const api = new ApiClient();


