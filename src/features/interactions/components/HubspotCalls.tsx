import { useHubspotCalls } from "../hooks/useHubspotCalls";
import { HubspotCallRows } from "./HubspotCallRows";

/** The HubSpot calls Vocify has not read yet, with their Transcribe action; nothing when there are none. */
export function HubspotCalls({ authorUserId, enabled = true }: { authorUserId: string | null; enabled?: boolean }) {
  const { calls, transcribe } = useHubspotCalls({ authorUserId, enabled });
  if (!enabled || calls.length === 0) return null;
  return (
    <HubspotCallRows
      calls={calls}
      busyId={transcribe.isPending ? transcribe.variables ?? null : null}
      onTranscribe={transcribe.mutateAsync}
    />
  );
}
