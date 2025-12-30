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
 * Clear stored tokens
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

  // Initialize token from storage
  useEffect(() => {
    const token = getStoredToken();
    if (token) {
      api.setToken(token);
    }
  }, []);

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
    clearTokens();
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
  }, []);

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


