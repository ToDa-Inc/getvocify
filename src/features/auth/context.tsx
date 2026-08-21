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
  useState,
  type ReactNode 
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getTokenExpiryMs } from '@/lib/auth-session';
import { api, ApiError } from '@/shared/lib/api-client';
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
  const [hasStoredSession, setHasStoredSession] = useState(() => !!getStoredToken());

  useEffect(() => {
    const token = getStoredToken();
    if (token) {
      api.setToken(token);
    }
    api.setOnAuthCleared(() => {
      setHasStoredSession(false);
      queryClient.setQueryData<User | null>(authKeys.me(), null);
      queryClient.clear();
      if (window.location.pathname.startsWith('/dashboard')) {
        window.location.replace('/login');
      }
    });
    return () => api.setOnAuthCleared(null);
  }, [queryClient]);

  const { data: user, isLoading, refetch } = useQuery({
    queryKey: authKeys.me(),
    queryFn: authApi.me,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 401) return false;
      return failureCount < 2;
    },
    staleTime: Infinity,
    enabled: hasStoredSession,
  });

  const login = useCallback(async (credentials: LoginCredentials): Promise<void> => {
    const response = await authApi.login(credentials);
    storeTokens(response.accessToken, response.refreshToken);
    setHasStoredSession(true);
    queryClient.setQueryData<User>(authKeys.me(), response.user);
  }, [queryClient]);

  const signup = useCallback(async (data: SignupData): Promise<void> => {
    const response = await authApi.signup(data);
    storeTokens(response.accessToken, response.refreshToken);
    setHasStoredSession(true);
    queryClient.setQueryData<User>(authKeys.me(), response.user);
  }, [queryClient]);

  const logout = useCallback(async (): Promise<void> => {
    try {
      await authApi.logout();
    } catch {
      // Ignore logout errors
    }
    setHasStoredSession(false);
    api.clearAllAuth();
    queryClient.setQueryData<User | null>(authKeys.me(), null);
    queryClient.clear();
  }, [queryClient]);

  const refresh = useCallback(async (): Promise<void> => {
    const token = await api.refreshSession();
    if (!token) {
      throw new Error('Session refresh failed');
    }
    await queryClient.invalidateQueries({ queryKey: authKeys.me() });
  }, [queryClient]);

  const restoreSession = useCallback(async () => {
    try {
      await api.refreshSession();
    } catch {
      // ignore
    }
    return refetch();
  }, [refetch]);

  useEffect(() => {
    if (!hasStoredSession) return;

    const checkAndRefresh = async () => {
      const t = getStoredToken();
      if (!t) return;
      const exp = getTokenExpiryMs(t);
      if (!exp || exp - Date.now() > REFRESH_BEFORE_EXPIRY_MS) return;
      try {
        await refresh();
      } catch {
        // 503/network: keep the stored session. Real 401 already cleared it.
      }
    };

    const id = setInterval(checkAndRefresh, 30_000);
    checkAndRefresh();
    return () => clearInterval(id);
  }, [refresh, hasStoredSession]);

  const value: AuthContextValue = {
    user: user ?? null,
    isLoading: hasStoredSession && isLoading && !user,
    isAuthenticated: hasStoredSession && !!user,
    hasStoredSession,
    restoreSession,
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


