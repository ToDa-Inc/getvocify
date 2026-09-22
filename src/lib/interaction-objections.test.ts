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
    const es = productCatalog.ES;
    const en = productCatalog.EN;
    const none = objectionReview({ coverage: "complete", patterns: [], notes: [], canPlaySpan: true, copy: es });
    assert.equal(none.claimNone, true);
    assert.equal(none.title, es.objectionsNoneDetected);
    const noneEn = objectionReview({ coverage: "complete", patterns: [], notes: [], canPlaySpan: true, copy: en });
    assert.equal(noneEn.title, en.objectionsNoneDetected);
  });

  it("does not claim absence when the analysis is partial", () => {
    const es = productCatalog.ES;
    const en = productCatalog.EN;
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
      copy: es,
    });
    assert.equal(partial.claimNone, false);
    assert.equal(partial.title, es.objectionsPartialAnalysis);
    assert.equal(partial.patterns[0].prospect_quotes[0], "está caro");
    const partialEn = objectionReview({
      coverage: "partial",
      patterns: partial.patterns,
      notes: [],
      canPlaySpan: true,
      copy: en,
    });
    assert.equal(partialEn.title, en.objectionsPartialAnalysis);
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
    const es = productCatalog.ES;
    const en = productCatalog.EN;
    const review = objectionReview({
      coverage: "complete",
      patterns: [],
      notes: [{ annotation_id: "note-1", text: "Lo dijo con ironía", offset_ms: 134000, author_id: "user-a", turn_id: null }],
      canPlaySpan: true,
      copy: es,
    });
    assert.equal(review.notes[0].playable, false);
    assert.equal(review.notes[0].label, es.noteLabel);
    assert.equal(review.notes[0].offset_ms, 134000);
    assert.equal(review.claimNone, false);
    assert.equal(noteFieldLabel("error", es), es.noteSaveFailed);
    assert.equal(noteFieldLabel("saved", en), en.noteSaved);
    assert.equal(noteFieldLabel("syncing", en), en.noteSaving);
    const merged = mergeNotes(
      [{ annotation_id: "note-1", text: "guardada", offset_ms: 1, author_id: "user-a" }],
      [{ annotation_id: "note-1", text: "duplicada", offset_ms: 1, author_id: "user-a" }, { annotation_id: "note-2", text: "nueva", offset_ms: 2, author_id: "user-a" }],
    );
    assert.deepEqual(merged.map((note) => note.annotation_id), ["note-1", "note-2"]);
  });
});
