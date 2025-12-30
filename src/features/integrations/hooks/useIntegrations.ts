/**
 * useIntegrations Hook
 * 
 * Fetches and manages CRM connections.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { integrationsApi, integrationKeys } from '../api';
import type { CRMProvider } from '../types';

/**
 * Hook to fetch all CRM connections
 */
export function useIntegrations() {
  return useQuery({
    queryKey: integrationKeys.connections(),
    queryFn: integrationsApi.listConnections,
  });
}

/**
 * Hook to fetch a specific connection
 */
export function useConnection(provider: CRMProvider) {
  return useQuery({
    queryKey: integrationKeys.connection(provider),
    queryFn: () => integrationsApi.getConnection(provider),
    enabled: !!provider,
  });
}

/**
 * Hook to fetch CRM deal schema
 */
export function useDealSchema(provider: CRMProvider) {
  return useQuery({
    queryKey: integrationKeys.schema(provider),
    queryFn: () => integrationsApi.getDealSchema(provider),
    enabled: !!provider,
    staleTime: 1000 * 60 * 60, // 1 hour - schema doesn't change often
  });
}

/**
 * Hook to disconnect a CRM
 */
export function useDisconnect() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (provider: CRMProvider) => integrationsApi.disconnect(provider),
    onSuccess: (_, provider) => {
      // Remove connection from cache
      queryClient.setQueryData(integrationKeys.connection(provider), null);
      // Invalidate connections list
      queryClient.invalidateQueries({ queryKey: integrationKeys.connections() });
    },
  });
}

/**
 * Hook to test a connection
 */
export function useTestConnection() {
  return useMutation({
    mutationFn: (provider: CRMProvider) => integrationsApi.testConnection(provider),
  });
}

/**
 * Hook to start OAuth flow
 */
export function useConnectCRM() {
  return useMutation({
    mutationFn: async (provider: CRMProvider) => {
      const { authorizationUrl } = await integrationsApi.getAuthorizationUrl(provider);
      // Redirect to OAuth provider
      window.location.href = authorizationUrl;
    },
  });
}


