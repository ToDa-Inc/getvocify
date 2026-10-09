import { useQuery } from "@tanstack/react-query";
import { debriefNeedsPoll } from "@shared/ui/components/debrief.js";
import { api } from "@/shared/lib/api-client";
import type { BriefView } from "@/lib/post-brief";

const POLL_MS = 2000;
// ~80 s: the coaching is written right after the call is read; past that it is a job issue.
const POLL_MAX = 40;

export function usePostInteractionBrief(memoId: string, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ["post-brief", memoId],
    enabled,
    queryFn: () => api.get<BriefView>(`/memos/${memoId}/brief`),
    // Keep asking while it is being written (pending, or partial and still waiting for the score).
    refetchInterval: (query) =>
      query.state.data && debriefNeedsPoll(query.state.data) && query.state.dataUpdateCount < POLL_MAX ? POLL_MS : false,
  });
}
