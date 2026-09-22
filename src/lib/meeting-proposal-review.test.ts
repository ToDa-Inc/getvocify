import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  MEETING_PROPOSAL_READ_ERROR_TITLE,
  meetingProposalReadErrorView,
  meetingProposalReviewSurface,
} from "./meeting-proposal-review.ts";

const agreed = { agreement: "agreed", starts_at: "2026-09-29T15:00:00+00:00", proposal_id: "p1" };

describe("meetingProposalReviewSurface", () => {
  it("shows pending while extraction runs or the proposal query is fetching", () => {
    assert.equal(
      meetingProposalReviewSurface({
        extractionPending: true,
        queryFetchStatus: "idle",
        queryIsPending: true,
        queryIsError: false,
        proposal: null,
      }).kind,
      "pending",
    );
    assert.equal(
      meetingProposalReviewSurface({
        extractionPending: false,
        queryFetchStatus: "fetching",
        queryIsPending: true,
        queryIsError: false,
        proposal: null,
      }).kind,
      "pending",
    );
  });

  it("does not treat a disabled idle query as loading", () => {
    assert.equal(
      meetingProposalReviewSurface({
        extractionPending: true,
        queryFetchStatus: "idle",
        queryIsPending: true,
        queryIsError: false,
        proposal: null,
      }).kind,
      "pending",
    );
  });

  it("surfaces a read error without buttons when the GET fails empty", () => {
    assert.equal(
      meetingProposalReviewSurface({
        extractionPending: false,
        queryFetchStatus: "idle",
        queryIsPending: false,
        queryIsError: true,
        proposal: null,
      }).kind,
      "read-error",
    );
    const view = meetingProposalReadErrorView();
    assert.equal(view.title, MEETING_PROPOSAL_READ_ERROR_TITLE);
    assert.equal(view.save, false);
    assert.equal(view.omit, false);
    assert.equal(view.startsAt, null);
  });

  it("keeps a successful empty proposal hidden and shows data when present", () => {
    assert.equal(
      meetingProposalReviewSurface({
        extractionPending: false,
        queryFetchStatus: "idle",
        queryIsPending: false,
        queryIsError: false,
        proposal: null,
      }).kind,
      "hidden",
    );
    assert.equal(
      meetingProposalReviewSurface({
        extractionPending: false,
        queryFetchStatus: "idle",
        queryIsPending: false,
        queryIsError: false,
        proposal: agreed,
      }).kind,
      "proposal",
    );
  });

  it("prefers cached proposal over a refetch error", () => {
    assert.equal(
      meetingProposalReviewSurface({
        extractionPending: false,
        queryFetchStatus: "idle",
        queryIsPending: false,
        queryIsError: true,
        proposal: agreed,
      }).kind,
      "proposal",
    );
  });
});
