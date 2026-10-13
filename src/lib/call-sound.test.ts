import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { CallSound } from "./call-sound.ts";

const quiet = () => new Int16Array(1600); // 100 ms at 16 kHz
const voice = () => Int16Array.from({ length: 1600 }, (_, i) => (i % 2 ? 3000 : -3000));

describe("CallSound", () => {
  it("times the call's sound by the audio sent, silence included", () => {
    const sound = new CallSound(16000);
    for (let i = 0; i < 10; i++) sound.hear(quiet());
    for (let i = 0; i < 5; i++) sound.hear(voice());
    sound.hear(quiet());
    assert.equal(Math.round(sound.heardS * 10) / 10, 1.6);
    assert.equal(sound.audible(0, 0.9), false);
    assert.equal(sound.audible(0.9, 1.05), true);
    assert.equal(sound.audible(1.55, 3), false);
  });

  it("forgets sound too old to matter", () => {
    const sound = new CallSound(16000);
    sound.hear(voice());
    for (let i = 0; i < 400; i++) sound.hear(quiet());
    assert.equal(sound.audible(0, 0.1), false);
  });
});
