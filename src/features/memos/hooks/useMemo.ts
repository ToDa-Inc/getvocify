/**
 * useMemo Hook
 * 
 * Fetches a single memo by ID and provides mutation hooks.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { memosApi, memoKeys } from '../api';
import type { Memo, ApproveMemoPayload } from '../types';

/**
 * Hook to fetch a single memo
 */
export function useMemo(id: string) {
  return useQuery({
    queryKey: memoKeys.detail(id),
    queryFn: () => memosApi.get(id),
    enabled: !!id,
    // Poll for status updates while processing
    refetchInterval: (query) => {
      const memo = query.state.data;
      if (!memo) return false;
      
      // Poll every 2 seconds while processing
      const processingStates = ['uploading', 'transcribing', 'extracting'];
      if (processingStates.includes(memo.status)) {
        return 2000;
      }
      return false;
    },
  });
}

/**
 * Hook to approve a memo
 */
export function useApproveMemo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload?: ApproveMemoPayload }) =>
      memosApi.approve(id, payload),
    onSuccess: (updatedMemo) => {
      // Update the memo in cache
      queryClient.setQueryData<Memo>(
        memoKeys.detail(updatedMemo.id),
        updatedMemo
      );
      // Invalidate the list to refresh
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
    },
  });
}

/**
 * Hook to reject a memo
 */
export function useRejectMemo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => memosApi.reject(id),
    onSuccess: (updatedMemo) => {
      queryClient.setQueryData<Memo>(
        memoKeys.detail(updatedMemo.id),
        updatedMemo
      );
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
    },
  });
}

/**
 * Hook to re-extract data from a memo
 */
export function useReExtractMemo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => memosApi.reExtract(id),
    onSuccess: (updatedMemo) => {
      queryClient.setQueryData<Memo>(
        memoKeys.detail(updatedMemo.id),
        updatedMemo
      );
    },
  });
}

/**
 * Hook to delete a memo
 */
export function useDeleteMemo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => memosApi.delete(id),
    onSuccess: (_, id) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: memoKeys.detail(id) });
      // Invalidate list
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
    },
  });
}


