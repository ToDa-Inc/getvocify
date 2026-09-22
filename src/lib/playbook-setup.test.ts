import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { applyPublishResult, motionAfterImport, playbookNotice } from "./playbook-setup.ts";

describe("playbook setup", () => {
  it("tells a member they cannot edit and an admin they can start", () => {
    const empty = {};
    const member = playbookNotice("member", empty);
    const admin = playbookNotice("admin", empty);
    assert.equal(member.showNotice, true);
    assert.equal(member.canEdit, false);
    assert.match(member.message, /administrador/);
    assert.equal(admin.canEdit, true);
    assert.match(admin.message, /publícalo/);
  });

  it("keeps the notice while a draft or import exists", () => {
    const notice = playbookNotice("owner", { discovery: "draft", qualification: "importing" });
    assert.equal(notice.showNotice, true);
    assert.deepEqual(notice.publishedKeys, []);
  });

  it("publishing discovery does not mark the other motions as done", () => {
    const notice = playbookNotice("owner", { discovery: "published", qualification: "missing" });
    assert.deepEqual(notice.publishedKeys, ["discovery"]);
    assert.equal(notice.showNotice, true);
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
    const drafted = motionAfterImport("missing", { status: "ready", published: false, reason: null });
    assert.equal(drafted.status, "draft");
    assert.equal(drafted.error, null);
  });
});
