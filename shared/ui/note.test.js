import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { noteOffsetMsFromPlaybackSeconds, noteOffsetMsFromReviewAudio, noteSaveBody } from "./note.js";

describe("review note", () => {
  it("does not save a blank note and keeps a real offset", () => {
    assert.equal(noteSaveBody("   ", 10), null);
    assert.deepEqual(noteSaveBody("Lo dijo con ironía", 134000.4), {
      text: "Lo dijo con ironía",
      offset_ms: 134000,
    });
    assert.deepEqual(noteSaveBody("sin tiempo", -3), { text: "sin tiempo", offset_ms: 0 });
  });

  it("turns playback seconds into offset_ms", () => {
    assert.equal(noteOffsetMsFromPlaybackSeconds(12.4), 12400);
    assert.equal(noteOffsetMsFromPlaybackSeconds(undefined), 0);
  });

  it("uses review audio currentTime when a source is loaded", () => {
    assert.equal(noteOffsetMsFromReviewAudio(null), 0);
    assert.equal(noteOffsetMsFromReviewAudio({ currentSrc: "", currentTime: 99 }), 0);
    assert.equal(
      noteOffsetMsFromReviewAudio({ currentSrc: "blob:audio", currentTime: 134.2 }),
      134200,
    );
  });
});
