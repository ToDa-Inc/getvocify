import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { appliedEchoCancellation, openRepMic } from "./rep-mic.ts";

/** A stream whose first audio track reports these settings. */
function streamWith(settings: Record<string, unknown>): MediaStream {
  return { getAudioTracks: () => [{ getSettings: () => settings }] } as unknown as MediaStream;
}

describe("appliedEchoCancellation", () => {
  it("reads the string all as all", () => {
    assert.equal(appliedEchoCancellation({ echoCancellation: "all" } as unknown as MediaTrackSettings), "all");
  });

  it("reads true and remote-only as the browser's own canceller", () => {
    assert.equal(appliedEchoCancellation({ echoCancellation: true }), "browser");
    assert.equal(appliedEchoCancellation({ echoCancellation: "remote-only" } as unknown as MediaTrackSettings), "browser");
  });

  it("reads false or a missing setting as off", () => {
    assert.equal(appliedEchoCancellation({ echoCancellation: false }), "off");
    assert.equal(appliedEchoCancellation({}), "off");
  });
});

describe("openRepMic", () => {
  it("asks for echo cancellation of everything the computer plays, and reports it applied", async () => {
    const asked: MediaStreamConstraints[] = [];
    const mic = await openRepMic(async (constraints) => {
      asked.push(constraints);
      return streamWith({ echoCancellation: "all" });
    });
    assert.deepEqual(asked, [{ audio: { echoCancellation: { ideal: "all" }, noiseSuppression: true, autoGainControl: true } }]);
    assert.equal(mic.echoCancellation, "all");
  });

  it("reports the browser's own canceller when an older Chromium read the value as true", async () => {
    const mic = await openRepMic(async () => streamWith({ echoCancellation: true }));
    assert.equal(mic.echoCancellation, "browser");
  });

  it("asks once more the way it always did when the browser refuses the value, and reports what that applied", async () => {
    const asked: MediaStreamConstraints[] = [];
    const mic = await openRepMic(async (constraints) => {
      asked.push(constraints);
      if (asked.length === 1) throw new TypeError("not a valid value for echoCancellation");
      return streamWith({ echoCancellation: true });
    });
    assert.deepEqual(asked[1], { audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    assert.equal(asked.length, 2);
    assert.equal(mic.echoCancellation, "browser");
  });

  it("falls back the same way on an OverconstrainedError", async () => {
    let calls = 0;
    const mic = await openRepMic(async () => {
      if (++calls === 1) throw Object.assign(new Error("constraint not satisfied"), { name: "OverconstrainedError" });
      return streamWith({ echoCancellation: false });
    });
    assert.equal(calls, 2);
    assert.equal(mic.echoCancellation, "off");
  });

  it("rethrows a permission refusal untouched, without a second ask", async () => {
    const refusal = Object.assign(new Error("Permission denied"), { name: "NotAllowedError" });
    let calls = 0;
    await assert.rejects(
      openRepMic(async () => {
        calls++;
        throw refusal;
      }),
      (error) => error === refusal,
    );
    assert.equal(calls, 1);
  });
});
