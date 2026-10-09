import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { EchoSuppressor, HOP_SAMPLES, SAMPLE_RATE } from "./echo-suppressor.ts";

/**
 * Speech-like test audio: noise whose loudness follows a pattern of "words" and pauses. The suppressor listens to
 * loudness only, so this stands in for speech without needing recordings.
 */
function words(seconds: number, seed: number, loudness = 6000): Float32Array {
  let state = seed >>> 0;
  const noise = () => ((state = (state * 1664525 + 1013904223) >>> 0) / 4294967296) * 2 - 1;
  const out = new Float32Array(Math.floor(seconds * SAMPLE_RATE));
  let i = 0;
  while (i < out.length) {
    const word = Math.floor((0.15 + 0.35 * Math.abs(noise())) * SAMPLE_RATE);
    const pause = Math.floor((0.05 + 0.3 * Math.abs(noise())) * SAMPLE_RATE);
    const level = loudness * (0.4 + 0.6 * Math.abs(noise()));
    for (let k = 0; k < word && i + k < out.length; k++) out[i + k] = noise() * level * Math.sin((Math.PI * k) / word);
    i += word + pause;
  }
  return out;
}

/** The mic: `near` plus the call heard through speakers (`gain`, `delayMs`, and a short smear), all as PCM16. */
function heard(call: Float32Array, near: Float32Array, gain: number, delayMs: number) {
  const delay = Math.floor((delayMs / 1000) * SAMPLE_RATE);
  const mic = new Int16Array(call.length);
  for (let n = 0; n < mic.length; n++) {
    let echo = 0;
    for (let k = 0; k < 6; k++) echo += (n - delay - k * 40 >= 0 ? call[n - delay - k * 40] : 0) * Math.pow(0.7, k);
    mic[n] = Math.max(-32768, Math.min(32767, Math.round(near[n] + echo * gain * 0.4)));
  }
  return { callPcm: Int16Array.from(call, (v) => Math.round(v)), mic };
}

/** Feeds both streams as the app does (call 100 ms at a time, mic 4096 samples at a time) and returns the mic as sent. */
function run(callPcm: Int16Array, mic: Int16Array, options?: ConstructorParameters<typeof EchoSuppressor>[0]) {
  const suppressor = new EchoSuppressor(options);
  const start = 50_000;
  const events: { at: number; kind: "call" | "mic"; from: number; length: number }[] = [];
  for (let from = 0; from + 1600 <= callPcm.length; from += 1600) events.push({ at: start + ((from + 1600) / SAMPLE_RATE) * 1000 + 20, kind: "call", from, length: 1600 });
  for (let from = 0; from + 4096 <= mic.length; from += 4096) events.push({ at: start + ((from + 4096) / SAMPLE_RATE) * 1000, kind: "mic", from, length: 4096 });
  events.sort((a, b) => a.at - b.at);
  const sent = new Int16Array(mic.length);
  for (const event of events) {
    if (event.kind === "call") suppressor.pushCall(callPcm.subarray(event.from, event.from + event.length), event.at);
    else sent.set(suppressor.process(mic.subarray(event.from, event.from + event.length), event.at), event.from);
  }
  return { sent, suppressor };
}

const energy = (a: Int16Array, from: number, to: number) => {
  let sum = 0;
  for (let i = from; i < to; i++) sum += a[i] * a[i];
  return sum;
};

describe("the echo suppressor", () => {
  it("mutes the call heard through speakers", () => {
    const call = words(30, 1);
    const { callPcm, mic } = heard(call, new Float32Array(call.length), 1, 90);
    const { sent } = run(callPcm, mic);
    // It needs a few seconds of both sides to know the delay, then it holds it (the first words of a call are not judged).
    const from = 15 * SAMPLE_RATE;
    const kept = energy(sent, from, sent.length) / energy(mic, from, mic.length);
    assert.ok(kept < 0.2, `kept ${(kept * 100).toFixed(0)}% of the echo's energy`);
  });

  it("never touches the rep's voice when the call is silent", () => {
    const call = new Float32Array(30 * SAMPLE_RATE);
    const near = words(30, 2);
    const { callPcm, mic } = heard(call, near, 1, 90);
    const { sent, suppressor } = run(callPcm, mic);
    const fed = Math.floor(mic.length / 4096) * 4096;
    assert.deepEqual(Array.from(sent.subarray(0, fed)), Array.from(mic.subarray(0, fed)));
    assert.equal(suppressor.stats().muted, 0);
  });

  it("keeps the rep's voice while the call talks too", () => {
    const call = words(40, 3);
    const near = words(40, 4, 9000);
    const { callPcm, mic } = heard(call, near, 1, 90);
    const { sent } = run(callPcm, mic);
    const from = 10 * SAMPLE_RATE;
    // What reaches the transcript must still be mostly the rep: the mic's energy minus the echo's, kept.
    const kept = energy(sent, from, sent.length) / energy(mic, from, mic.length);
    assert.ok(kept > 0.75, `kept only ${(kept * 100).toFixed(0)}% of the rep's energy`);
  });

  it("copes with the call's audio arriving late and unevenly", () => {
    const call = words(30, 5);
    const { callPcm, mic } = heard(call, new Float32Array(call.length), 1, 140);
    const { sent } = run(callPcm, mic);
    const from = 10 * SAMPLE_RATE;
    assert.ok(energy(sent, from, sent.length) / energy(mic, from, mic.length) < 0.25);
  });

  it("leaves the microphone as it is when it is unrelated to the call", () => {
    const call = words(30, 6);
    const other = words(30, 7);
    const { callPcm } = heard(call, new Float32Array(call.length), 1, 90);
    const mic = Int16Array.from(other, (v) => Math.round(v));
    const { sent } = run(callPcm, mic);
    // Two unrelated voices: the call's loudness does not predict the mic's.
    assert.ok(energy(sent, 0, sent.length) / energy(mic, 0, mic.length) > 0.9);
  });

  it("returns a chunk of the same length and counts what it muted", () => {
    const suppressor = new EchoSuppressor();
    const out = suppressor.process(new Int16Array(4096), 10_000);
    assert.equal(out.length, 4096);
    assert.deepEqual(suppressor.stats(), { hops: Math.ceil(4096 / HOP_SAMPLES), muted: 0 });
  });
});
