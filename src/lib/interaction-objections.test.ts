import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { noteFieldLabel, objectionReview } from "./interaction-objections.ts";

describe("objection review", () => {
  it("says none were detected only when the read is complete and empty", () => {
    const none = objectionReview({ coverage: "complete", patterns: [], notes: [], canPlaySpan: true });
    assert.equal(none.claimNone, true);
    assert.equal(none.title, "No se detectaron objeciones.");
  });

  it("does not claim absence when the analysis is partial", () => {
    const partial = objectionReview({
      coverage: "partial",
      patterns: [{
        pattern_id: "pat-1",
        category: "price",
        kind: "objection",
        resolution: "open",
        response: null,
        prospect_quotes: ["está caro"],
      }],
      notes: [],
      canPlaySpan: true,
    });
    assert.equal(partial.claimNone, false);
    assert.match(partial.title ?? "", /No se puede afirmar/);
    assert.equal(partial.patterns[0].prospect_quotes[0], "está caro");
  });

  it("shows offset and author for a note that has no turn, without playback", () => {
    const review = objectionReview({
      coverage: "complete",
      patterns: [],
      notes: [{ annotation_id: "note-1", text: "Lo dijo con ironía", offset_ms: 134000, author_id: "user-a", turn_id: null }],
      canPlaySpan: true,
    });
    assert.equal(review.notes[0].playable, false);
    assert.equal(review.notes[0].label, "Nota");
    assert.equal(review.notes[0].offset_ms, 134000);
    assert.equal(review.claimNone, false);
    assert.equal(noteFieldLabel("error"), "No se pudo guardar la nota");
  });
});
