import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { IDLE_CALL, isCallEnded, isCallUp, reduceCall, type DialTarget } from "./call-engine-state.ts";

const ANA: DialTarget = {
  to: "+34600111222",
  name: "Ana Ruiz",
  contactId: "901",
  dealId: null,
  callerId: "+34910000000",
};

const dialing = () => reduceCall(IDLE_CALL, { type: "dial", target: ANA });
const live = () =>
  reduceCall(reduceCall(reduceCall(dialing(), { type: "callSid", callSid: "CA1" }), { type: "ringing" }), {
    type: "accepted",
    at: 1000,
  });

describe("reduceCall", () => {
  it("a dial connects to the target", () => {
    const s = dialing();
    assert.equal(s.phase, "connecting");
    assert.equal(s.target, ANA);
    assert.equal(isCallUp(s), true);
  });

  it("an answered call is active from the answer time", () => {
    const s = live();
    assert.deepEqual([s.phase, s.callSid, s.answeredAt, s.answered], ["active", "CA1", 1000, true]);
  });

  it("hanging up ends the call and keeps who it was with", () => {
    const s = reduceCall(live(), { type: "ended", at: 5000 });
    assert.deepEqual([s.phase, s.endedAt, s.target, s.answered], ["idle", 5000, ANA, true]);
    assert.equal(isCallEnded(s), true);
    assert.equal(isCallUp(s), false);
  });

  it("a carrier outcome before the answer explains the end", () => {
    let s = reduceCall(dialing(), { type: "outcome", message: "Busy" });
    s = reduceCall(s, { type: "ended", at: 2000 });
    assert.deepEqual([s.outcome, s.answered], ["Busy", false]);
  });

  it("the carrier outcome can arrive after the hang-up", () => {
    const ended = reduceCall(dialing(), { type: "ended", at: 2000 });
    assert.equal(reduceCall(ended, { type: "outcome", message: "No answer" }).outcome, "No answer");
  });

  it("an answered call never shows a missed-call outcome", () => {
    assert.equal(reduceCall(live(), { type: "outcome", message: "No answer" }).outcome, null);
  });

  it("a second dial while a call is up is ignored", () => {
    const s = reduceCall(dialing(), { type: "dial", target: { ...ANA, to: "+1555" } });
    assert.equal(s.target, ANA);
  });

  it("a new dial after an ended call starts clean", () => {
    let s = reduceCall(reduceCall(dialing(), { type: "outcome", message: "Busy" }), { type: "ended", at: 1 });
    s = reduceCall(s, { type: "dial", target: ANA });
    assert.deepEqual([s.phase, s.outcome, s.endedAt, s.answered], ["connecting", null, null, false]);
  });

  it("mute only applies to an active call and is cleared at the end", () => {
    assert.equal(reduceCall(dialing(), { type: "muted", muted: true }).muted, false);
    const muted = reduceCall(live(), { type: "muted", muted: true });
    assert.equal(muted.muted, true);
    assert.equal(reduceCall(muted, { type: "ended", at: 9 }).muted, false);
  });

  it("remote audio counts as answered (parked Telnyx legs never send accept)", () => {
    assert.equal(reduceCall(dialing(), { type: "remoteAudio" }).answered, true);
  });

  it("a failure is remembered with its message", () => {
    const s = reduceCall(dialing(), { type: "failed", message: "No caller ID" });
    assert.deepEqual([s.failed, s.error], [true, "No caller ID"]);
  });

  it("reset forgets the ended call", () => {
    const ended = reduceCall(live(), { type: "ended", at: 5 });
    assert.deepEqual(reduceCall(ended, { type: "reset" }), IDLE_CALL);
    assert.equal(reduceCall(live(), { type: "reset" }).phase, "active");
  });
});
