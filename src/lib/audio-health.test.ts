import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { AudioHealth, CALL_SILENT_MS, MIC_SILENT_MS } from "./audio-health.ts";

const zeros = new Int16Array(1600);
const hiss = Int16Array.from({ length: 1600 }, (_, i) => (i % 2 ? 6 : -6));
const voice = Int16Array.from({ length: 1600 }, (_, i) => Math.round(4000 * Math.sin(i / 5)));

describe("AudioHealth", () => {
  it("says nothing while both sides carry sound", () => {
    const health = new AudioHealth(0, { watchCall: true });
    for (let t = 0; t <= 40_000; t += 100) {
      health.hear("you", hiss, t);
      health.hear("them", hiss, t);
    }
    assert.equal(health.issue(40_000), null);
  });

  it("flags a mic that sends only zeros", () => {
    const health = new AudioHealth(0, { watchCall: true });
    for (let t = 0; t <= MIC_SILENT_MS; t += 100) health.hear("you", zeros, t);
    assert.equal(health.issue(MIC_SILENT_MS - 100), null);
    assert.equal(health.issue(MIC_SILENT_MS), "mic");
  });

  it("clears once the mic sends sound again", () => {
    const health = new AudioHealth(0, { watchCall: false });
    assert.equal(health.issue(MIC_SILENT_MS), "mic");
    health.hear("you", hiss, MIC_SILENT_MS + 100);
    assert.equal(health.issue(MIC_SILENT_MS + 100), null);
  });

  it("does not flag a quiet other side while the rep is silent too", () => {
    const health = new AudioHealth(0, { watchCall: true });
    for (let t = 0; t <= 60_000; t += 100) {
      health.hear("you", hiss, t);
      health.hear("them", zeros, t);
    }
    assert.equal(health.issue(60_000), null);
  });

  it("flags call audio that stays zeros while the rep talks", () => {
    const health = new AudioHealth(0, { watchCall: true });
    for (let t = 0; t <= CALL_SILENT_MS; t += 100) {
      health.hear("you", voice, t);
      health.hear("them", zeros, t);
    }
    assert.equal(health.issue(CALL_SILENT_MS), "call");
  });

  it("never flags call audio when it isn't watched", () => {
    const health = new AudioHealth(0, { watchCall: false });
    for (let t = 0; t <= CALL_SILENT_MS; t += 100) health.hear("you", voice, t);
    assert.equal(health.issue(CALL_SILENT_MS), null);
  });

  it("starts the waits again after a pause", () => {
    const health = new AudioHealth(0, { watchCall: true });
    assert.equal(health.issue(MIC_SILENT_MS), "mic");
    health.restart(20_000);
    assert.equal(health.issue(20_000 + MIC_SILENT_MS - 100), null);
  });
});
