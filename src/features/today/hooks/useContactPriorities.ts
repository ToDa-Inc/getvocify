import { useQuery } from "@tanstack/react-query";
import { contactPrioritiesApi, contactPriorityKeys } from "../api";

export function useContactPriorities({ fresh = false }: { fresh?: boolean } = {}) {
  return useQuery({
    queryKey: contactPriorityKeys.list(),
    queryFn: () => contactPrioritiesApi.list(),
    placeholderData: (previous) => previous,
    refetchInterval: (query) => (query.state.data?.stale ? 5000 : false),
    ...(fresh ? { staleTime: 0, refetchOnWindowFocus: true } : {}),
  });
}
