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
export function mapAuthResponse(raw: Record<string, unknown>): AuthResponse {
  return {
    user: mapRawUser((raw.user as Record<string, unknown>) ?? {}),
    accessToken: String(raw.access_token ?? ''),
    refreshToken: String(raw.refresh_token ?? ''),
    expiresIn: (raw.expires_in as number) || 3600,
  };
}

export function mapRawUser(raw: Record<string, unknown>): User {
  const companyRaw = raw.company as Record<string, unknown> | null | undefined;
  return {
    id: raw.id as string,
    email: (raw.email as string) || '',
    fullName: (raw.full_name as string) ?? null,
    companyName: (raw.company_name as string) ?? null,
    avatarUrl: (raw.avatar_url as string) ?? null,
    phone: (raw.phone as string) ?? null,
    autoCreateContactCompany: Boolean(raw.auto_create_contact_company),
    productContext: (raw.product_context as string) ?? '',
    sttLanguages: Array.isArray(raw.stt_languages)
      ? (raw.stt_languages as string[])
      : ['es'],
    createdAt: (raw.created_at as string) || '',
    company: companyRaw
      ? {
          id: String(companyRaw.id),
          name: String(companyRaw.name ?? ''),
          role: (companyRaw.role as 'owner' | 'admin' | 'member') ?? 'member',
          seatLimit: Number(companyRaw.seat_limit ?? 1),
          seatsUsed: Number(companyRaw.seats_used ?? 0),
          seatsPending: Number(companyRaw.seats_pending ?? 0),
          accessMode: String(companyRaw.access_mode ?? 'open'),
          billingStatus: String(companyRaw.billing_status ?? 'none'),
          planType:
            companyRaw.plan_type === 'starter' || companyRaw.plan_type === 'pro'
              ? companyRaw.plan_type
              : null,
          paywalled: Boolean(companyRaw.paywalled),
          canUseDialer:
            companyRaw.can_use_dialer == null ? true : Boolean(companyRaw.can_use_dialer),
        }
      : null,
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
    
    return mapAuthResponse(raw);
  },

  /**
   * Log in with email and password
   */
  login: async (credentials: LoginCredentials): Promise<AuthResponse> => {
    const raw = await api.post<Record<string, unknown>>('/auth/login', credentials);
    return mapAuthResponse(raw);
  },

  /**
   * Log out the current user
   */
  logout: (): Promise<void> => {
    return api.post<void>('/auth/logout');
  },

  /**
   * Refresh the access token.
   *
   * 401 = refresh token is dead (sign in again). 503 = Auth is down or the
   * GoTrue oauth_client_id bug fired — keep the stored session and retry.
   */
  refresh: async (refreshToken: string): Promise<RefreshResponse> => {
    const accessToken = localStorage.getItem('vocify_token');
    const raw = await api.post<Record<string, unknown>>('/auth/refresh', {
      refresh_token: refreshToken,
      ...(accessToken && accessToken !== 'undefined' && accessToken !== 'null'
        ? { access_token: accessToken }
        : {}),
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
    const body: Record<string, unknown> = {
      full_name: data.fullName,
      company_name: data.companyName,
      avatar_url: data.avatarUrl,
      phone: data.phone,
    };
    if (data.autoCreateContactCompany !== undefined) {
      body.auto_create_contact_company = data.autoCreateContactCompany;
    }
    if (data.productContext !== undefined) {
      body.product_context = data.productContext;
    }
    if (data.sttLanguages !== undefined) {
      body.stt_languages = data.sttLanguages;
    }
    const raw = await api.patch<Record<string, unknown>>('/auth/me', body);
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


