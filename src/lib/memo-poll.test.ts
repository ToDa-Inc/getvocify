import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { shouldPollMemo, transcriptPolishSettled } from "./memo-poll.ts";

describe("shouldPollMemo", () => {
  it("polls while transcribing or extracting", () => {
    assert.equal(shouldPollMemo({ status: "transcribing" }), true);
    assert.equal(shouldPollMemo({ status: "extracting" }), true);
  });

  it("stops after polish lands after extract", () => {
    const memo = {
      status: "pending_review",
      processedAt: "2026-08-21T13:10:57.000Z",
      pipelineMeta: {
        stages: [
          { name: "extract", at: "2026-08-21T13:10:57.000Z" },
          { name: "sanitize", at: "2026-08-21T13:11:03.000Z" },
        ],
      },
    };
    assert.equal(transcriptPolishSettled(memo), true);
    assert.equal(shouldPollMemo(memo, Date.parse("2026-08-21T13:11:04.000Z")), false);
  });

  it("keeps polling pending_review until polish or the window elapses", () => {
    const memo = {
      status: "pending_review",
      processedAt: "2026-08-21T13:10:57.000Z",
      pipelineMeta: { stages: [{ name: "extract", at: "2026-08-21T13:10:57.000Z" }] },
    };
    assert.equal(shouldPollMemo(memo, Date.parse("2026-08-21T13:11:05.000Z")), true);
    assert.equal(shouldPollMemo(memo, Date.parse("2026-08-21T13:11:30.000Z")), false);
  });
});
