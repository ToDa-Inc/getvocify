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

/** Map backend snake_case user to frontend camelCase User */
function mapRawUser(raw: Record<string, unknown>): User {
  return {
    id: raw.id as string,
    email: (raw.email as string) || '',
    fullName: (raw.full_name as string) ?? null,
    companyName: (raw.company_name as string) ?? null,
    avatarUrl: (raw.avatar_url as string) ?? null,
    phone: (raw.phone as string) ?? null,
    createdAt: (raw.created_at as string) || '',
  };
}

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
    
    return {
      user: mapRawUser((raw.user as Record<string, unknown>) ?? {}),
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
    
    return {
      user: mapRawUser((raw.user as Record<string, unknown>) ?? {}),
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
  refresh: async (refreshToken: string): Promise<RefreshResponse> => {
    const raw = await api.post<Record<string, unknown>>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    return {
      accessToken: raw.access_token as string,
      refreshToken: (raw.refresh_token as string) ?? undefined,
      expiresIn: (raw.expires_in as number) ?? 3600,
    };
  },

  /**
   * Get the current authenticated user
   */
  me: async (): Promise<User> => {
    const raw = await api.get<Record<string, unknown>>('/auth/me');
    return mapRawUser(raw);
  },

  /**
   * Update the current user's profile
   */
  updateProfile: async (data: UpdateProfileData): Promise<User> => {
    const raw = await api.patch<Record<string, unknown>>('/auth/me', {
      full_name: data.fullName,
      company_name: data.companyName,
      avatar_url: data.avatarUrl,
      phone: data.phone,
    });
    return mapRawUser(raw);
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


