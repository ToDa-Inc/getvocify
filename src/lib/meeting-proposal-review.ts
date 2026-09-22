/** How memo review surfaces meeting proposals while the GET is in flight. */

export type MeetingProposalReviewInput = {
  extractionPending: boolean;
  queryFetchStatus: "fetching" | "paused" | "idle";
  queryIsPending: boolean;
  queryIsError: boolean;
  proposal: Record<string, unknown> | null;
};

export type MeetingProposalReviewSurface =
  | { kind: "pending" }
  | { kind: "read-error" }
  | { kind: "hidden" }
  | { kind: "proposal" };

export const MEETING_PROPOSAL_READ_ERROR_TITLE = "No se pudo leer la reunión";

export function meetingProposalReviewSurface(input: MeetingProposalReviewInput): MeetingProposalReviewSurface {
  const queryLoading =
    !input.extractionPending && input.queryIsPending && input.queryFetchStatus === "fetching";
  if (input.extractionPending || queryLoading) return { kind: "pending" };
  if (input.queryIsError && input.proposal === null) return { kind: "read-error" };
  if (input.proposal === null) return { kind: "hidden" };
  return { kind: "proposal" };
}

export function meetingProposalReadErrorView() {
  return {
    visible: true as const,
    title: MEETING_PROPOSAL_READ_ERROR_TITLE,
    startsAt: null,
    save: false,
    omit: false,
  };
}
