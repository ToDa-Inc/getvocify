import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { applyPublishResult, importReview, motionAfterImport, playbookNotice } from "./playbook-setup.ts";

const playbooksSectionSource = readFileSync(
  fileURLToPath(new URL("../features/playbooks/components/PlaybooksSection.tsx", import.meta.url)),
  "utf8",
);

describe("playbook setup", () => {
  it("tells a member they cannot edit and an admin they can start", () => {
    const empty = {};
    const member = playbookNotice("member", empty);
    const admin = playbookNotice("admin", empty);
    assert.equal(member.showNotice, true);
    assert.equal(member.canEdit, false);
    assert.equal(member.message, "playbookNoticeAdmin");
    assert.equal(admin.canEdit, true);
    assert.equal(admin.message, "playbookNoticeStart");
  });

  it("keeps the notice while a draft or import exists", () => {
    const notice = playbookNotice("owner", { discovery: "draft", qualification: "importing" });
    assert.equal(notice.showNotice, true);
    assert.equal(notice.message, "playbookNoticeDraft");
    assert.deepEqual(notice.publishedKeys, []);
  });

  it("publishing discovery does not mark the other motions as done", () => {
    const notice = playbookNotice("owner", { discovery: "published", qualification: "missing" });
    assert.deepEqual(notice.publishedKeys, ["discovery"]);
    assert.equal(notice.showNotice, true);
    assert.equal(notice.message, "playbookNoticeMissing");
  });

  it("a rejected publish leaves the draft, and discovery does not publish the rest", () => {
    const motions = { discovery: "draft", qualification: "missing", closing: "missing" };
    assert.deepEqual(applyPublishResult(motions, "discovery", { ok: false }), motions);
    const next = applyPublishResult(motions, "discovery", {
      ok: true,
      salesMotionKey: "discovery",
      status: "published",
    });
    assert.equal(next.discovery, "published");
    assert.equal(next.qualification, "missing");
    assert.equal(next.closing, "missing");
    assert.deepEqual(
      applyPublishResult({ discovery: "missing" }, "discovery", {
        ok: true,
        salesMotionKey: "qualification",
        status: "published",
      }),
      { discovery: "missing" },
    );
  });

  it("completes setup with imports only, not an AI interview", () => {
    assert.doesNotMatch(playbooksSectionSource, /\/ask|copilot|interview|entrevista/i);
    assert.match(playbooksSectionSource, /\/playbooks\/imports/);
    assert.match(playbooksSectionSource, /\/playbooks\/types/);
    const review = importReview({
      status: "ready",
      published: false,
      draft: { text: "Confirmar el problema antes del precio." },
    });
    assert.equal(review.canPublish, true);
    assert.equal(review.status, "draft");
  });

  it("a pdf without text does not replace a published motion", () => {
    const failed = motionAfterImport("published", {
      status: "failed",
      published: false,
      reason: "pdf_has_no_text",
    });
    assert.equal(failed.status, "published");
    assert.equal(failed.error, "playbookPdfNoText");
    const locked = motionAfterImport("published", {
      status: "failed",
      published: false,
      reason: "pdf_encrypted",
    });
    assert.equal(locked.status, "published");
    assert.equal(locked.error, "playbookPdfEncrypted");
    const conflict = importReview({
      status: "ready",
      published: false,
      draft: { text: "Nunca descuentes. Siempre cierra.", contradictions: ["siempre/nunca"] },
    });
    assert.equal(conflict.canPublish, false);
    assert.equal(conflict.status, "draft");
    assert.equal(conflict.warning, "playbookContradiction");
    assert.equal(conflict.text.startsWith("Nunca"), true);
    const drafted = motionAfterImport("missing", { status: "ready", published: false, reason: null });
    assert.equal(drafted.status, "draft");
    assert.equal(drafted.error, null);
  });
});
