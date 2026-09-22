import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { productCatalog } from "./product-catalog.ts";
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
    assert.equal(postBriefFetchTitle("loading", productCatalog.ES), productCatalog.ES.briefNotReady);
    assert.equal(postBriefFetchTitle("error", productCatalog.ES), productCatalog.ES.briefReadFailed);
    assert.equal(postBriefFetchTitle("loading", productCatalog.EN), productCatalog.EN.briefNotReady);
    assert.equal(postBriefFetchTitle("error", productCatalog.EN), productCatalog.EN.briefReadFailed);
  });

  it("shows a missing brief without pretending the job is running", () => {
    const surface = briefSurface(
      {
        status: "pending",
        reason: "not_started",
        input_revision: "",
        sections: [],
        audio_available: false,
        strength: null,
        improvement: null,
        waiting: false,
      },
      productCatalog.ES,
    );
    assert.equal(surface.title, productCatalog.ES.briefNotReady);
    assert.equal(surface.waiting, false);
    assert.equal(surface.strength, null);
    const en = briefSurface(
      {
        status: "pending",
        reason: "not_started",
        input_revision: "",
        sections: [],
        audio_available: false,
        strength: null,
        improvement: null,
        waiting: false,
      },
      productCatalog.EN,
    );
    assert.equal(en.title, productCatalog.EN.briefNotReady);
  });

  it("keeps the same revision when a partial brief becomes ready", () => {
    const before = briefSurface(partial, productCatalog.ES);
    const after = briefSurface(
      { ...partial, status: "ready", strength: "Nombró el precio", improvement: "No cerró el paso" },
      productCatalog.ES,
    );
    assert.equal(before.revision, after.revision);
    assert.equal(before.sections[0].evidence_refs[0], after.sections[0].evidence_refs[0]);
    assert.equal(after.strength, "Nombró el precio");
  });

  it("keeps the quote readable when the audio is gone", () => {
    const surface = briefSurface(partial, productCatalog.ES);
    assert.equal(surface.sections[0].quote, "está caro");
    assert.equal(surface.playable, false);
    assert.equal(surface.audioNote, productCatalog.ES.briefAudioUnavailable);
    assert.equal(briefSurface(partial, productCatalog.EN).audioNote, productCatalog.EN.briefAudioUnavailable);
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
    const highlight = {
      highlight_mode: "deferred" as const,
      highlight_at: "2026-09-22T16:30:00Z",
      timezone: "Europe/Madrid",
    };
    const deferred = highlightScheduleLine(highlight, productCatalog.ES);
    assert.equal(deferred, "Se destaca a las 18:30");
    assert.equal(highlightScheduleLine({ ...highlight, highlight_mode: "immediate" }, productCatalog.ES), null);
    assert.equal(highlightScheduleLine(highlight, productCatalog.EN), "Highlighted at 18:30");
    const surface = briefSurface(
      {
        ...partial,
        status: "ready",
        highlight: {
          highlight_mode: "end_of_day",
          highlight_at: "2026-09-22T16:00:00Z",
          timezone: "Europe/Madrid",
        },
      },
      productCatalog.ES,
    );
    assert.match(surface.highlightNote ?? "", /Se destaca a las/);
  });

  it("turns a failure into a partial retry without inventing sections", () => {
    const failed = briefSurface({ ...partial, status: "failed", reason: "job_error" }, productCatalog.ES);
    assert.equal(failed.title, productCatalog.ES.briefTitleFailed);
    assert.equal(failed.waiting, false);
    const retried = retryBrief({ ...partial, status: "failed", reason: "job_error" });
    assert.equal(retried.status, "partial");
    assert.deepEqual(retried.sections, partial.sections);
    const skipped = briefSurface(
      { ...partial, status: "skipped", sections: [], reason: "no_conversation" },
      productCatalog.EN,
    );
    assert.equal(skipped.waiting, false);
    assert.equal(skipped.title, productCatalog.EN.briefTitleSkipped);
  });
});
