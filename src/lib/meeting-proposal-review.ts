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

export function meetingProposalReviewSurface(input: MeetingProposalReviewInput): MeetingProposalReviewSurface {
  const queryLoading =
    !input.extractionPending && input.queryIsPending && input.queryFetchStatus === "fetching";
  if (input.extractionPending || queryLoading) return { kind: "pending" };
  if (input.queryIsError && input.proposal === null) return { kind: "read-error" };
  if (input.proposal === null) return { kind: "hidden" };
  return { kind: "proposal" };
}

export type MeetingProposalPhrases = {
  save: string;
  omit: string;
  reconcile: string;
};

export function meetingProposalReadErrorView(title: string, phrases: MeetingProposalPhrases) {
  return {
    visible: true as const,
    title,
    startsAt: null,
    save: false,
    omit: false,
    phrases,
  };
}
