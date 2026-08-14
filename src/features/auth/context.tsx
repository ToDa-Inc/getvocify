/**
 * Auth Context
 * 
 * Provides authentication state and actions throughout the app.
 */

import { 
  createContext, 
  useContext, 
  useCallback, 
  useEffect,
  type ReactNode 
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/lib/api-client';
import { authApi, authKeys } from './api';
import type { 
  User, 
  LoginCredentials, 
  SignupData,
  AuthContextValue 
} from './types';

// Storage keys
const TOKEN_KEY = 'vocify_token';
const REFRESH_KEY = 'vocify_refresh';

/** Refresh token 10 minutes before expiry to avoid 401s during long flows (e.g. Step 2→3) */
const REFRESH_BEFORE_EXPIRY_MS = 10 * 60 * 1000;

/**
 * Get stored token
 */
function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Decode JWT exp (expiry) in seconds. Returns null if invalid.
 */
function getTokenExpiryMs(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload?.exp ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

/**
 * Store tokens
 */
function storeTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_KEY, refreshToken);
  api.setToken(accessToken);
}

/**
 * Clear stored tokens (used by logout)
 */
function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  api.clearToken();
}

// Create context
const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * Auth Provider Component
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const queryClient = useQueryClient();

  // Initialize token from storage and wire auth-cleared callback
  useEffect(() => {
    const token = getStoredToken();
    if (token) {
      api.setToken(token);
    }
    api.setOnAuthCleared(() => {
      queryClient.setQueryData<User | null>(authKeys.me(), null);
      queryClient.clear();
      // Redirect to login when session is invalid (401, refresh failed)
      if (window.location.pathname.startsWith('/dashboard')) {
        window.location.replace('/login');
      }
    });
    return () => api.setOnAuthCleared(null);
  }, [queryClient]);

  // Query current user
  const { data: user, isLoading } = useQuery({
    queryKey: authKeys.me(),
    queryFn: authApi.me,
    retry: false,
    staleTime: Infinity,
    enabled: !!getStoredToken(),
  });

  /**
   * Log in with credentials
   */
  const login = useCallback(async (credentials: LoginCredentials): Promise<void> => {
    const response = await authApi.login(credentials);
    storeTokens(response.accessToken, response.refreshToken);
    queryClient.setQueryData<User>(authKeys.me(), response.user);
  }, [queryClient]);

  /**
   * Sign up new user
   */
  const signup = useCallback(async (data: SignupData): Promise<void> => {
    const response = await authApi.signup(data);
    storeTokens(response.accessToken, response.refreshToken);
    queryClient.setQueryData<User>(authKeys.me(), response.user);
  }, [queryClient]);

  /**
   * Log out current user
   */
  const logout = useCallback(async (): Promise<void> => {
    try {
      await authApi.logout();
    } catch {
      // Ignore logout errors
    }
    api.clearAllAuth();
    queryClient.setQueryData<User | null>(authKeys.me(), null);
    queryClient.clear();
  }, [queryClient]);

  /**
   * Refresh the session
   */
  const refresh = useCallback(async (): Promise<void> => {
    const refreshToken = localStorage.getItem(REFRESH_KEY);
    if (!refreshToken) {
      throw new Error('No refresh token');
    }

    const response = await authApi.refresh(refreshToken);
    localStorage.setItem(TOKEN_KEY, response.accessToken);
    api.setToken(response.accessToken);
    if (response.refreshToken) {
      localStorage.setItem(REFRESH_KEY, response.refreshToken);
    }
  }, []);

  // Proactive refresh: renew token ~5 min before expiry to avoid 401s
  useEffect(() => {
    const token = getStoredToken();
    if (!token) return;

    const checkAndRefresh = async () => {
      const t = getStoredToken();
      if (!t) return;
      const exp = getTokenExpiryMs(t);
      if (!exp || exp - Date.now() > REFRESH_BEFORE_EXPIRY_MS) return;
      try {
        await refresh();
      } catch {
        // Refresh failed; 401 retry or next request will trigger clearAllAuth
      }
    };

    const id = setInterval(checkAndRefresh, 30_000);
    checkAndRefresh(); // run once on mount
    return () => clearInterval(id);
  }, [refresh]);

  const value: AuthContextValue = {
    user: user ?? null,
    isLoading,
    isAuthenticated: !!user,
    login,
    signup,
    logout,
    refresh,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Hook to access auth context
 */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}

/**
 * Hook to get current user (throws if not authenticated)
 */
export function useCurrentUser(): User {
  const { user, isAuthenticated } = useAuth();
  if (!isAuthenticated || !user) {
    throw new Error('User is not authenticated');
  }
  return user;
}


