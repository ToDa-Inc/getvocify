import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { memoKeys } from "@/features/memos/api";
import { recordingKeys, recordingsApi } from "@/features/recordings/api";
import type { CrmCallRecording, ProcessCallRecordingResponse, UnansweredOutcome } from "@/features/recordings/types";
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
  // Once Vocify has the call it is a conversation: it leaves this list at once rather than on the next refetch,
  // and a call the server did not turn into one is an error, not a quiet return to the button.
  const settle = (callId: string, result: ProcessCallRecordingResponse) => {
    if (!result?.memo_id) throw new Error("no memo");
    queryClient.setQueryData<CrmCallRecording[]>(recordingKeys.recent(authorUserId), (calls) =>
      calls?.map((call) => (call.call_id === callId ? { ...call, memo_id: result.memo_id, memo_status: result.status } : call)),
    );
    void queryClient.invalidateQueries({ queryKey: recordingKeys.all });
    void queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
    return result;
  };
  const transcribe = useMutation({
    mutationFn: async (callId: string) => settle(callId, await recordingsApi.process(callId)),
  });
  const markUnanswered = useMutation({
    mutationFn: async ({ callId, outcome }: { callId: string; outcome: UnansweredOutcome }) =>
      settle(callId, await recordingsApi.markUnanswered(callId, outcome)),
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
    busyId: transcribe.isPending
      ? (transcribe.variables ?? null)
      : markUnanswered.isPending
        ? (markUnanswered.variables?.callId ?? null)
        : null,
    transcribe: transcribe.mutateAsync,
    markUnanswered: (callId: string, outcome: UnansweredOutcome) => markUnanswered.mutateAsync({ callId, outcome }),
  };
}
