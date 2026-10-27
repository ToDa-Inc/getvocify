import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { memoKeys } from "@/features/memos/api";
import { recordingKeys, recordingsApi } from "@/features/recordings/api";
import { callDurationSeconds } from "@/lib/call-duration";
import type { CrmCallEntry } from "@/lib/interactions";

const STALE_MS = 60_000;

/**
 * Calls logged in the viewer's CRM that Vocify has not turned into a conversation yet, shaped for the
 * conversations list, with the action that does it. A call that already has a memo is in the list
 * as that memo. A company without a CRM that records calls gets an error: nothing is added then.
 */
export function useCrmCalls({ authorUserId, enabled = true }: { authorUserId: string | null; enabled?: boolean }) {
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
  const entries: CrmCallEntry[] = enabled
    ? (query.data ?? [])
        .filter((call) => call.has_recording && !call.memo_id)
        .flatMap((call) => {
          const at = call.timestamp ?? (call.timestamp_ms ? new Date(call.timestamp_ms).toISOString() : null);
          if (!at) return [];
          return [
            {
              id: call.call_id,
              createdAt: at,
              title: call.title,
              subtitle: [call.author_name?.trim(), call.to_number].filter(Boolean).join(" · "),
              seconds: callDurationSeconds(call),
            },
          ];
        })
    : [];
  return {
    entries,
    busyId: transcribe.isPending ? (transcribe.variables ?? null) : null,
    transcribe: transcribe.mutateAsync,
  };
}
