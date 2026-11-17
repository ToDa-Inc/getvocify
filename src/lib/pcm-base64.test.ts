import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { base64Of } from "./pcm-base64.ts";

function viaBtoa(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

describe("base64Of", () => {
  it("is btoa's text for every length and byte", () => {
    for (const length of [0, 1, 2, 3, 4, 5, 255, 256, 3198, 3199, 3200, 32000]) {
      const bytes = new Uint8Array(length).map((_, i) => (i * 37 + (i >> 3)) & 255);
      assert.equal(base64Of(bytes.buffer), viaBtoa(bytes.buffer), `length ${length}`);
    }
  });

  it("reuses its buffer without leaking an earlier, longer frame", () => {
    base64Of(new Uint8Array(3200).fill(255).buffer);
    assert.equal(base64Of(new Uint8Array([1, 2]).buffer), "AQI=");
  });
});
