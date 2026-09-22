import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { playbookNotice } from "./playbook-setup.ts";

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
});
