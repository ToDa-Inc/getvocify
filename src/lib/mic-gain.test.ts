import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { MicGain } from "./mic-gain.ts";

const tone = (amplitude: number) => Int16Array.from({ length: 1600 }, (_, i) => Math.round(amplitude * Math.sin(i / 5)));
const loudest = (samples: Int16Array) => samples.reduce((max, s) => Math.max(max, Math.abs(s)), 0);

describe("MicGain", () => {
  it("raises a quiet native mic by up to 8x", () => {
    assert.ok(Math.abs(loudest(new MicGain().apply(tone(1000))) - 8000) < 100);
  });

  it("raises a mic whose speech peaks at 4000 to the target, never past full scale", () => {
    const gain = new MicGain();
    assert.ok(Math.abs(loudest(gain.apply(tone(4000))) - 16000) < 100);
    assert.ok(loudest(gain.apply(tone(30000))) <= 32767);
  });

  it("leaves a loud mic as it is", () => {
    const samples = tone(20000);
    assert.equal(new MicGain().apply(samples), samples);
  });
});
