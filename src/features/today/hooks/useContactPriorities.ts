import { useQuery } from "@tanstack/react-query";
import { contactPrioritiesApi, contactPriorityKeys } from "../api";

export function useContactPriorities() {
  return useQuery({
    queryKey: contactPriorityKeys.list(),
    queryFn: () => contactPrioritiesApi.list(),
    placeholderData: (previous) => previous,
  });
}
