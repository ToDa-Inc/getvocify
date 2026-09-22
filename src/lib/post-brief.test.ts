import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  briefSurface,
  highlightScheduleLine,
  postBriefFetchTitle,
  requestBriefSectionPlay,
  retryBrief,
  type BriefView,
} from "./post-brief.ts";

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
  it("uses stable titles while the brief request is loading or fails", () => {
    assert.equal(postBriefFetchTitle("loading"), "El resumen todavía no está listo");
    assert.equal(postBriefFetchTitle("error"), "No se pudo leer el resumen");
  });

  it("shows a missing brief without pretending the job is running", () => {
    const surface = briefSurface({
      status: "pending",
      reason: "not_started",
      input_revision: "",
      sections: [],
      audio_available: false,
      strength: null,
      improvement: null,
      waiting: false,
    });
    assert.equal(surface.title, "El resumen todavía no está listo");
    assert.equal(surface.waiting, false);
    assert.equal(surface.strength, null);
  });

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

  it("calls onPlay at offset when playable", () => {
    let played: number | null = null;
    requestBriefSectionPlay(true, 12000, (ms) => {
      played = ms;
    });
    assert.equal(played, 12000);
    played = null;
    requestBriefSectionPlay(false, 12000, (ms) => {
      played = ms;
    });
    assert.equal(played, null);
  });

  it("shows deferred highlight time in user timezone and hides immediate scheduling", () => {
    const deferred = highlightScheduleLine({
      highlight_mode: "deferred",
      highlight_at: "2026-09-22T16:30:00Z",
      timezone: "Europe/Madrid",
    });
    assert.equal(deferred, "Se destaca a las 18:30");
    assert.equal(
      highlightScheduleLine({
        highlight_mode: "immediate",
        highlight_at: "2026-09-22T16:00:00Z",
        timezone: "Europe/Madrid",
      }),
      null,
    );
    const surface = briefSurface({
      ...partial,
      status: "ready",
      highlight: {
        highlight_mode: "end_of_day",
        highlight_at: "2026-09-22T16:00:00Z",
        timezone: "Europe/Madrid",
      },
    });
    assert.match(surface.highlightNote ?? "", /Se destaca a las/);
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
