import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { briefSurface, retryBrief, type BriefView } from "./post-brief.ts";

const partial: BriefView = {
  status: "partial",
  reason: "score_pending",
  input_revision: "rev-4",
  sections: [{ kind: "objections", evidence_refs: ["ev-1"], quote: "está caro", offset_ms: 12000 }],
  audio_available: false,
  strength: null,
  improvement: null,
  waiting: false,
};

describe("post interaction brief", () => {
  it("keeps the same revision when a partial brief becomes ready", () => {
    const before = briefSurface(partial);
    const after = briefSurface({ ...partial, status: "ready", strength: "Nombró el precio", improvement: "No cerró el paso" });
    assert.equal(before.revision, after.revision);
    assert.equal(before.sections[0].evidence_refs[0], after.sections[0].evidence_refs[0]);
    assert.equal(after.strength, "Nombró el precio");
  });

  it("keeps the quote readable when the audio is gone", () => {
    const surface = briefSurface(partial);
    assert.equal(surface.sections[0].quote, "está caro");
    assert.equal(surface.playable, false);
    assert.equal(surface.audioNote, "Audio no disponible");
  });

  it("turns a failure into a partial retry without inventing sections", () => {
    const failed = briefSurface({ ...partial, status: "failed", reason: "job_error" });
    assert.equal(failed.title, "No se pudo completar el resumen");
    assert.equal(failed.waiting, false);
    const retried = retryBrief({ ...partial, status: "failed", reason: "job_error" });
    assert.equal(retried.status, "partial");
    assert.deepEqual(retried.sections, partial.sections);
    const skipped = briefSurface({ ...partial, status: "skipped", sections: [], reason: "no_conversation" });
    assert.equal(skipped.waiting, false);
    assert.equal(skipped.title, "No hay conversación que resumir");
  });
});
