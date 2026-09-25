import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import type { BriefView } from "@/lib/post-brief";

export function usePostInteractionBrief(memoId: string) {
  return useQuery({
    queryKey: ["post-brief", memoId],
    queryFn: () => api.get<BriefView>(`/memos/${memoId}/brief`),
    refetchInterval: (query) => (query.state.data?.status === "pending" ? 1500 : false),
  });
}
