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
  signup: async (data: SignupData): Promise<AuthResponse> => {
    const raw = await api.post<Record<string, unknown>>('/auth/signup', {
      email: data.email,
      password: data.password,
      full_name: data.fullName,
      company_name: data.companyName,
    });
    
    // Map snake_case from backend to camelCase expected by frontend
    return {
      user: raw.user as User,
      accessToken: raw.access_token as string,
      refreshToken: raw.refresh_token as string,
      expiresIn: (raw.expires_in as number) || 3600,
    };
  },

  /**
   * Log in with email and password
   */
  login: async (credentials: LoginCredentials): Promise<AuthResponse> => {
    const raw = await api.post<Record<string, unknown>>('/auth/login', credentials);
    
    // Map snake_case from backend to camelCase expected by frontend
    return {
      user: raw.user as User,
      accessToken: raw.access_token as string,
      refreshToken: raw.refresh_token as string,
      expiresIn: (raw.expires_in as number) || 3600,
    };
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


