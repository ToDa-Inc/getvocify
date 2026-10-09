import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";

const FIVE_MINUTES = 5 * 60 * 1000;

/** Question ids this account can actually answer. Empty until the server says otherwise. */
export function useAskSuggestions(): string[] {
  const { data } = useQuery({
    queryKey: ["ask", "suggestions"],
    queryFn: () => api.get<{ suggestions: string[] }>("/ask/suggestions"),
    staleTime: FIVE_MINUTES,
    retry: false,
  });
  return data?.suggestions ?? [];
}
