import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { memoKeys } from "@/features/memos/api";
import { recordingKeys, recordingsApi } from "@/features/recordings/api";

const STALE_MS = 60_000;

/**
 * HubSpot calls with a recording that Vocify has not turned into a conversation yet. A call that
 * already has a memo is in the list as that memo, so it is left out here. A company without HubSpot
 * connected gets an error: the section stays hidden rather than showing one.
 */
export function useHubspotCalls({ authorUserId, enabled = true }: { authorUserId: string | null; enabled?: boolean }) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: recordingKeys.recent(authorUserId),
    queryFn: () => recordingsApi.listRecent(authorUserId),
    enabled,
    staleTime: STALE_MS,
    retry: false,
  });
  const transcribe = useMutation({
    mutationFn: (callId: string) => recordingsApi.process(callId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: recordingKeys.all });
      void queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
    },
  });
  const calls = (query.data ?? []).filter((call) => call.has_recording && !call.memo_id);
  return { calls, transcribe };
}
