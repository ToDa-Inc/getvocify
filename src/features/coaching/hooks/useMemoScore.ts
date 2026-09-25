import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import type { ScoreView } from "@/lib/coaching-score";

export function useMemoScore(memoId: string) {
  return useQuery({
    queryKey: ["memo-score", memoId],
    queryFn: () => api.get<ScoreView>(`/memos/${memoId}/score`),
    refetchInterval: (query) => (query.state.data?.status === "pending" ? 1500 : false),
  });
}
