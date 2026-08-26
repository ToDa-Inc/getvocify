import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyLiveResults,
  cloneAudioTracks,
  downsampleTo16k,
  EMPTY_TRANSCRIPT,
  floatToPcm16,
  LIVE_STT_SAMPLE_RATE,
  PCM_WORKLET_SOURCE,
} from "./live-stt.ts";

describe("downsampleTo16k", () => {
  it("leaves 16 kHz audio unchanged", () => {
    const input = new Float32Array([0.1, 0.2, 0.3]);
    assert.equal(downsampleTo16k(input, LIVE_STT_SAMPLE_RATE), input);
  });

  it("collapses 48 kHz frames to 16 kHz so Speechmatics hears real time", () => {
    const input = new Float32Array(48);
    for (let i = 0; i < 48; i++) input[i] = i < 16 ? 1 : 0;
    const out = downsampleTo16k(input, 48000);
    assert.equal(out.length, 16);
    assert.ok(out[0] > 0.5);
    assert.ok(out[15] < 0.2);
  });
});

describe("floatToPcm16", () => {
  it("encodes clipped samples as signed 16-bit", () => {
    const pcm = floatToPcm16(new Float32Array([1, 0, -1]), 16000);
    assert.equal(pcm.length, 3);
    assert.equal(pcm[0], 0x7fff);
    assert.equal(pcm[1], 0);
    assert.equal(pcm[2], -0x8000);
  });
});

describe("applyLiveResults", () => {
  it("keeps interim text from Speechmatics Results while speaking", () => {
    const next = applyLiveResults(EMPTY_TRANSCRIPT, {
      type: "Results",
      is_final: false,
      channel: { alternatives: [{ transcript: "hola" }] },
    });
    assert.deepEqual(next, { interim: "hola", final: "", full: "hola" });
  });

  it("appends finals so the live pane is not empty after a pause", () => {
    const interim = applyLiveResults(EMPTY_TRANSCRIPT, {
      type: "Results",
      is_final: false,
      provider: "speechmatics",
      channel: { alternatives: [{ transcript: "hola" }] },
    } as { type: string; is_final: boolean; channel: { alternatives: Array<{ transcript: string }> } });
    const done = applyLiveResults(interim!, {
      type: "Results",
      is_final: true,
      channel: { alternatives: [{ transcript: "hola mundo" }] },
    });
    assert.equal(done?.final, "hola mundo");
    assert.equal(done?.interim, "");
  });

  it("does not drop Results that omit provider (dashboard used to key only speechmatics)", () => {
    const next = applyLiveResults(EMPTY_TRANSCRIPT, {
      type: "Results",
      is_final: true,
      channel: { alternatives: [{ transcript: "ok" }] },
    });
    assert.equal(next?.final, "ok");
  });
});

describe("cloneAudioTracks", () => {
  it("clones audio tracks so MediaRecorder and live STT do not share one track", () => {
    const original = {
      id: "orig",
      clone() {
        return { ...this, id: "clone" };
      },
    };
    const cloned = cloneAudioTracks({ getAudioTracks: () => [original] });
    assert.equal(cloned[0].id, "clone");
    assert.notEqual(cloned[0], original);
  });
});

describe("PCM worklet", () => {
  it("downsamples inside the worklet when the context is not 16 kHz", () => {
    assert.match(PCM_WORKLET_SOURCE, /TARGET_RATE = 16000/);
    assert.match(PCM_WORKLET_SOURCE, /sampleRate/);
  });
});
