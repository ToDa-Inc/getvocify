import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { pollDelayMs, postCallFor, summarizeUpdates } from "./post-call.ts";

describe("summarizeUpdates", () => {
  it("names only real changes, first three, with the total", () => {
    const { updates, total } = summarizeUpdates([
      { field_label: "Lead status", current_value: "New", new_value: "Interested" },
      { field_label: "Phone", current_value: "+34 600", new_value: "+34 600" },
      { field_label: "Next step", new_value: "Call back Tuesday 10:00" },
      { field_label: "Budget", new_value: "" },
      { field_name: "notes", new_value: "Six reps, notes by hand after every call, CRM half empty" },
      { field_label: "Decision maker", new_value: "Sales director" },
    ]);
    assert.equal(total, 4);
    assert.deepEqual(updates, [
      { label: "Lead status", value: "Interested" },
      { label: "Next step", value: "Call back Tuesday 10:00" },
      { label: "notes", value: "Six reps, notes by hand after every call,…" },
    ]);
  });

  it("is empty when nothing would change", () => {
    assert.deepEqual(summarizeUpdates(undefined), { updates: [], total: 0 });
  });
});

describe("postCallFor", () => {
  const memo = { id: "m1", status: "pending_review", hubspotContactId: "879829962968" };

  it("writes while extraction runs", () => {
    assert.equal(postCallFor({ ...memo, status: "extracting" }, "Zadarma test").stage, "writing");
  });

  it("offers one click when the memo knows its contact", () => {
    const state = postCallFor(memo, "Zadarma test", [{ field_label: "Lead status", new_value: "Interested" }]);
    assert.equal(state.stage, "ready");
    assert.equal(state.canApprove, true);
    assert.equal(state.total, 1);
  });

  it("only offers review without a contact", () => {
    const state = postCallFor({ ...memo, hubspotContactId: null }, null, [{ field_label: "X", new_value: "y" }]);
    assert.equal(state.stage, "ready");
    assert.equal(state.canApprove, false);
  });

  it("is done when auto-approve already wrote it, and sends failures to review", () => {
    assert.equal(postCallFor({ ...memo, status: "approved" }, null).stage, "done");
    assert.equal(postCallFor({ ...memo, status: "failed" }, null).stage, "review");
  });

  it("has nothing to approve when nothing changes", () => {
    const state = postCallFor(memo, "Zadarma test", []);
    assert.equal(state.stage, "review");
    assert.equal(state.canApprove, false);
  });

  it("checks quickly at first, then gently", () => {
    assert.equal(pollDelayMs(0), 1500);
    assert.equal(pollDelayMs(30), 4000);
  });
});
