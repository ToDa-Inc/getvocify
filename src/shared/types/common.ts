/**
 * Common types used across the application
 */

/**
 * Standard API list response with pagination
 */
export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}

/**
 * Standard API error response shape
 */
export interface ApiErrorResponse {
  message: string;
  code?: string;
  details?: Record<string, string[]>;
}

/**
 * Generic ID type (UUIDs from Supabase)
 */
export type ID = string;

/**
 * ISO date string type for better documentation
 */
export type ISODateString = string;

/**
 * Nullable type helper
 */
export type Nullable<T> = T | null;

/**
 * Make specific properties optional
 */
export type PartialBy<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

/**
 * Make specific properties required
 */
export type RequiredBy<T, K extends keyof T> = Omit<T, K> & Required<Pick<T, K>>;

/**
 * Extract the element type from an array
 */
export type ArrayElement<T> = T extends readonly (infer E)[] ? E : never;

/**
 * Common async operation states
 */
export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error';

/**
 * Result type for operations that can fail
 */
export type Result<T, E = Error> =
  | { success: true; data: T }
  | { success: false; error: E };


