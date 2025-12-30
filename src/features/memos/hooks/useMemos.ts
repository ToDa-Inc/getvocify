/**
 * useMemos Hook
 * 
 * Fetches and manages the list of voice memos.
 */

import { useQuery } from '@tanstack/react-query';
import { memosApi, memoKeys } from '../api';
import type { MemoFilters } from '../types';

/**
 * Hook to fetch list of memos
 */
export function useMemos(filters?: MemoFilters) {
  return useQuery({
    queryKey: memoKeys.list(filters),
    queryFn: () => memosApi.list(filters),
  });
}


