/**
 * Auth API
 * 
 * All API calls related to authentication and user management.
 */

import { api } from '@/shared/lib/api-client';
import type {
  User,
  LoginCredentials,
  SignupData,
  AuthResponse,
  RefreshResponse,
  UpdateProfileData,
} from './types';

/**
 * Query keys for TanStack Query
 */
export const authKeys = {
  all: ['auth'] as const,
  me: () => [...authKeys.all, 'me'] as const,
};

/**
 * Auth API methods
 */
export const authApi = {
  /**
   * Sign up a new user
   */
  signup: (data: SignupData): Promise<AuthResponse> => {
    return api.post<AuthResponse>('/auth/signup', {
      email: data.email,
      password: data.password,
      full_name: data.fullName,
      company_name: data.companyName,
    });
  },

  /**
   * Log in with email and password
   */
  login: (credentials: LoginCredentials): Promise<AuthResponse> => {
    return api.post<AuthResponse>('/auth/login', credentials);
  },

  /**
   * Log out the current user
   */
  logout: (): Promise<void> => {
    return api.post<void>('/auth/logout');
  },

  /**
   * Refresh the access token
   */
  refresh: (refreshToken: string): Promise<RefreshResponse> => {
    return api.post<RefreshResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    });
  },

  /**
   * Get the current authenticated user
   */
  me: (): Promise<User> => {
    return api.get<User>('/auth/me');
  },

  /**
   * Update the current user's profile
   */
  updateProfile: (data: UpdateProfileData): Promise<User> => {
    return api.patch<User>('/auth/me', {
      full_name: data.fullName,
      company_name: data.companyName,
      avatar_url: data.avatarUrl,
    });
  },

  /**
   * Request a password reset email
   */
  requestPasswordReset: (email: string): Promise<void> => {
    return api.post<void>('/auth/reset-password', { email });
  },

  /**
   * Set a new password (with reset token)
   */
  setNewPassword: (token: string, password: string): Promise<void> => {
    return api.post<void>('/auth/reset-password/confirm', {
      token,
      password,
    });
  },
};


