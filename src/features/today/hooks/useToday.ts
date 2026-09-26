import { useQuery } from "@tanstack/react-query";
import { todayApi, todayKeys } from "../api";

export function useToday({ fresh = false }: { fresh?: boolean } = {}) {
  return useQuery({
    queryKey: todayKeys.view(),
    queryFn: () => todayApi.get(),
    placeholderData: (previous) => previous,
    refetchOnWindowFocus: true,
    ...(fresh ? { staleTime: 0 } : {}),
  });
}
