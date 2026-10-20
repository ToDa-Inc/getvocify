import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { addJob, dropJob, forIsland, patchJob, stateOfMemo, stopAutoOpen, type AfterCallJob } from "./after-call-jobs.ts";

const job = (id: string, extra: Partial<AfterCallJob> = {}): AfterCallJob => ({ id, name: id, state: "working", memoId: null, autoOpen: true, ...extra });

describe("after-call jobs", () => {
  it("a job is added once, patched by id and dropped", () => {
    let jobs = addJob([], job("a"));
    jobs = addJob(jobs, job("b"));
    jobs = addJob(jobs, job("a", { name: "again" }));
    assert.deepEqual(jobs.map((j) => j.id), ["b", "a"]);
    jobs = patchJob(jobs, "b", { state: "needs", memoId: "m" });
    assert.deepEqual(jobs.find((j) => j.id === "b"), { id: "b", name: "b", state: "needs", memoId: "m", autoOpen: true });
    assert.deepEqual(dropJob(jobs, "b").map((j) => j.id), ["a"]);
  });

  it("starting something else ends every job's right to open its card by itself", () => {
    const jobs = [job("a"), job("b", { autoOpen: false })];
    assert.deepEqual(stopAutoOpen(jobs).map((j) => j.autoOpen), [false, false]);
    assert.equal(stopAutoOpen(jobs.map((j) => ({ ...j, autoOpen: false }))).length, 2);
  });

  it("the island is told the id, the name and the state, nothing else", () => {
    assert.deepEqual(forIsland([job("a", { memoId: "m" })]), [{ id: "a", name: "a", state: "working" }]);
  });

  it("a memo leaves its job needing review, done, failed, or with a follow-up after a call nobody answered", () => {
    assert.equal(stateOfMemo({ status: "pending_review" }, true, false), "needs");
    assert.equal(stateOfMemo({ status: "approved" }, true, false), "done");
    assert.equal(stateOfMemo({ status: "failed" }, true, false), "failed");
    assert.equal(stateOfMemo({ hubspotContactId: "42" }, true, true), "followup");
    assert.equal(stateOfMemo({ hubspotContactId: "42" }, false, true), "done", "no CRM: nothing to follow up in");
    assert.equal(stateOfMemo({}, true, true), "done", "no contact: nothing to follow up on");
  });
});
