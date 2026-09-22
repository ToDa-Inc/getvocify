import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { applyPublishResult, importReview, motionAfterImport, playbookNotice } from "./playbook-setup.ts";

describe("playbook setup", () => {
  it("tells a member they cannot edit and an admin they can start", () => {
    const empty = {};
    const member = playbookNotice("member", empty);
    const admin = playbookNotice("admin", empty);
    assert.equal(member.showNotice, true);
    assert.equal(member.canEdit, false);
    assert.match(member.message, /administrador/);
    assert.equal(admin.canEdit, true);
    assert.match(admin.message, /coaching/);
  });

  it("keeps the notice while a draft or import exists", () => {
    const notice = playbookNotice("owner", { discovery: "draft", qualification: "importing" });
    assert.equal(notice.showNotice, true);
    assert.match(notice.message, /pendiente de publicar/);
    assert.deepEqual(notice.publishedKeys, []);
  });

  it("publishing discovery does not mark the other motions as done", () => {
    const notice = playbookNotice("owner", { discovery: "published", qualification: "missing" });
    assert.deepEqual(notice.publishedKeys, ["discovery"]);
    assert.equal(notice.showNotice, true);
    assert.match(notice.message, /pendientes/);
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

  it("a pdf without text does not replace a published motion", () => {
    const failed = motionAfterImport("published", {
      status: "failed",
      published: false,
      reason: "pdf_has_no_text",
    });
    assert.equal(failed.status, "published");
    assert.match(failed.error || "", /PDF/);
    const locked = motionAfterImport("published", {
      status: "failed",
      published: false,
      reason: "pdf_encrypted",
    });
    assert.equal(locked.status, "published");
    assert.match(locked.error || "", /protegido/);
    const conflict = importReview({
      status: "ready",
      published: false,
      draft: { text: "Nunca descuentes. Siempre cierra.", contradictions: ["siempre/nunca"] },
    });
    assert.equal(conflict.canPublish, false);
    assert.equal(conflict.status, "draft");
    assert.match(conflict.warning || "", /contradictorios/);
    assert.equal(conflict.text.startsWith("Nunca"), true);
    const drafted = motionAfterImport("missing", { status: "ready", published: false, reason: null });
    assert.equal(drafted.status, "draft");
    assert.equal(drafted.error, null);
  });
});
