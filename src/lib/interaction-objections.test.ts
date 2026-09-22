import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
import {
  mergeNotes,
  noteFieldLabel,
  objectionReview,
  patternCategoryLabel,
  patternKindLabel,
  patternResolutionLabel,
} from "./interaction-objections.ts";

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
    const en = productCatalog.EN;
    const es = productCatalog.ES;
    assert.equal(patternCategoryLabel("price", en), "Price");
    assert.equal(patternCategoryLabel("price", es), "Precio");
    assert.equal(patternCategoryLabel("status_quo", es), "Statu quo");
    assert.equal(patternCategoryLabel("custom_key", es), "custom_key");
    assert.equal(patternKindLabel("objection", es), "Objeción");
    assert.equal(patternKindLabel("obstacle", en), "Obstacle");
    assert.equal(patternKindLabel("unknown", en), "Unclassified");
    assert.equal(patternResolutionLabel("resolved", es), "Resuelta");
    assert.equal(patternResolutionLabel("open", en), "Open");
    assert.equal(patternResolutionLabel("unknown", es), "Sin dato");
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
    const merged = mergeNotes(
      [{ annotation_id: "note-1", text: "guardada", offset_ms: 1, author_id: "user-a" }],
      [{ annotation_id: "note-1", text: "duplicada", offset_ms: 1, author_id: "user-a" }, { annotation_id: "note-2", text: "nueva", offset_ms: 2, author_id: "user-a" }],
    );
    assert.deepEqual(merged.map((note) => note.annotation_id), ["note-1", "note-2"]);
  });
});
