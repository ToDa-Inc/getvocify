/**
 * Types for the Auth feature
 * 
 * User authentication, session management, and profile data.
 */

import type { ID, ISODateString, Nullable } from '@/shared/types/common';

// ============================================
// USER TYPES
// ============================================

/**
 * User entity
 * 
 * Represents an authenticated user in the system.
 * Combines Supabase auth.users with our user_profiles table.
 */
export interface User {
  /** Unique identifier (from Supabase Auth) */
  id: ID;
  /** Email address (primary identifier) */
  email: string;
  /** Full name */
  fullName: Nullable<string>;
  /** Company or organization name */
  companyName: Nullable<string>;
  /** Avatar URL (from OAuth or uploaded) */
  avatarUrl: Nullable<string>;
  /** Phone (E.164) for WhatsApp */
  phone?: Nullable<string>;
  /** When true, create contact/company from memo extraction; when false, only update deals */
  autoCreateContactCompany: boolean;
  /** When the user was created */
  createdAt: ISODateString;
}

/**
 * Get user's display name (full name or email prefix)
 */
export function getUserDisplayName(user: User): string {
  if (user.fullName) return user.fullName;
  if (user.email) return user.email.split('@')[0];
  return 'User';
}

/**
 * Get user's initials for avatar fallback
 */
export function getUserInitials(user: User): string {
  if (user.fullName) {
    const parts = user.fullName.trim().split(/\s+/);
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
    }
    return parts[0].slice(0, 2).toUpperCase();
  }
  return user.email.slice(0, 2).toUpperCase();
}

// ============================================
// AUTH REQUEST TYPES
// ============================================

/**
 * Login credentials
 */
export interface LoginCredentials {
  /** Email address */
  email: string;
  /** Password */
  password: string;
}

/**
 * Signup form data
 */
export interface SignupData {
  /** Email address */
  email: string;
  /** Password (min 8 chars) */
  password: string;
  /** Full name */
  fullName: string;
  /** Company name (optional) */
  companyName?: string;
}

/**
 * Password reset request
 */
export interface ResetPasswordRequest {
  /** Email address */
  email: string;
}

/**
 * New password submission
 */
export interface NewPasswordData {
  /** New password */
  password: string;
  /** Password confirmation */
  confirmPassword: string;
}

/**
 * Profile update data
 */
export interface UpdateProfileData {
  /** Full name */
  fullName?: string;
  /** Company name */
  companyName?: string;
  /** Avatar URL */
  avatarUrl?: string;
  /** Phone (E.164) for WhatsApp sender lookup */
  phone?: string;
  /** Create contact/company when extraction contains that data; false = deal-only updates */
  autoCreateContactCompany?: boolean;
}

// ============================================
// AUTH RESPONSE TYPES
// ============================================

/**
 * Response from login/signup endpoints
 */
export interface AuthResponse {
  /** Authenticated user */
  user: User;
  /** JWT access token */
  accessToken: string;
  /** Refresh token for getting new access tokens */
  refreshToken: string;
  /** Token expiration time in seconds */
  expiresIn: number;
}

/**
 * Response from token refresh endpoint
 */
export interface RefreshResponse {
  /** New JWT access token */
  accessToken: string;
  /** New refresh token (if rotated by Supabase) */
  refreshToken?: string;
  /** Token expiration time in seconds */
  expiresIn: number;
}

// ============================================
// AUTH STATE TYPES
// ============================================

/**
 * Authentication state for context
 */
export interface AuthState {
  /** Current authenticated user (null if not logged in) */
  user: Nullable<User>;
  /** Whether auth state is being loaded */
  isLoading: boolean;
  /** Whether user is authenticated */
  isAuthenticated: boolean;
}

/**
 * Auth context value with actions
 */
export interface AuthContextValue extends AuthState {
  /** Log in with email/password */
  login: (credentials: LoginCredentials) => Promise<void>;
  /** Sign up new user */
  signup: (data: SignupData) => Promise<void>;
  /** Log out current user */
  logout: () => Promise<void>;
  /** Refresh the current session */
  refresh: () => Promise<void>;
}


