import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { isManagerRole, navItemsFor, usesRepHome, type NavItem } from "./nav.ts";

const home: NavItem = { id: "home", labelKey: "navHome", path: "/dashboard" };
const memos: NavItem = { id: "memos", labelKey: "navMemos", path: "/dashboard/memos" };
const copilot: NavItem = { id: "copilot", labelKey: "navCopilot", path: "/dashboard/copilot", beta: true };
const ask: NavItem = { id: "ask", labelKey: "navAsk", path: "/dashboard/ask" };
const insights: NavItem = { id: "insights", labelKey: "navInsights", path: "/dashboard/insights" };
const settings: NavItem = { id: "settings", labelKey: "navSettings", path: "/dashboard/settings" };
const call: NavItem = { id: "call", labelKey: "navCall" };

const today: NavItem = { ...home, labelKey: "navToday" };
const conversations: NavItem = { ...memos, labelKey: "navConversations" };

describe("navItemsFor with the rep workspace off", () => {
  it("gives a member the current menu and plans card", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: false }), {
      items: [home, memos, copilot, ask, settings, call],
      showPlans: true,
    });
  });

  it("adds Team for owners and admins, as today", () => {
    for (const role of ["owner", "admin"]) {
      assert.deepEqual(navItemsFor({ role, repWorkspace: false }), {
        items: [home, memos, copilot, ask, insights, settings, call],
        showPlans: true,
      });
    }
  });

  it("treats a missing flag or role like today", () => {
    assert.deepEqual(navItemsFor({ role: "member" }), navItemsFor({ role: "member", repWorkspace: false }));
    assert.deepEqual(navItemsFor({ role: null }), navItemsFor({ role: "member", repWorkspace: false }));
    assert.deepEqual(navItemsFor({}), navItemsFor({ role: "member", repWorkspace: false }));
  });
});

describe("navItemsFor with the rep workspace on", () => {
  it("gives a member the short rep menu without Copilot, Team or plans", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: true }), {
      items: [today, conversations, ask, call, settings],
      showPlans: false,
    });
  });

  it("gives owners and admins the rep menu plus Team, Copilot and plans", () => {
    for (const role of ["owner", "admin"]) {
      assert.deepEqual(navItemsFor({ role, repWorkspace: true }), {
        items: [today, conversations, copilot, ask, call, insights, settings],
        showPlans: true,
      });
    }
  });

  it("keeps every entry on the same route as today", () => {
    const before = new Map(navItemsFor({ role: "owner" }).items.map((item) => [item.id, item.path]));
    for (const role of ["member", "owner"]) {
      for (const item of navItemsFor({ role, repWorkspace: true }).items) {
        assert.equal(item.path, before.get(item.id), item.id);
      }
    }
  });

  it("does not treat an unknown role as a manager", () => {
    assert.deepEqual(navItemsFor({ role: "viewer", repWorkspace: true }), navItemsFor({ role: "member", repWorkspace: true }));
    assert.deepEqual(navItemsFor({ role: undefined, repWorkspace: true }), navItemsFor({ role: "member", repWorkspace: true }));
  });
});

describe("isManagerRole", () => {
  it("is owner or admin only", () => {
    assert.equal(isManagerRole("owner"), true);
    assert.equal(isManagerRole("admin"), true);
    assert.equal(isManagerRole("member"), false);
    assert.equal(isManagerRole(null), false);
    assert.equal(isManagerRole(undefined), false);
  });
});

describe("usesRepHome", () => {
  it("follows only company.repWorkspace", () => {
    assert.equal(usesRepHome({ repWorkspace: true }), true);
    assert.equal(usesRepHome({ repWorkspace: true, role: "member" }), true);
    assert.equal(usesRepHome({ repWorkspace: false, role: "owner" }), false);
    assert.equal(usesRepHome({ role: "owner" }), false);
    assert.equal(usesRepHome(null), false);
    assert.equal(usesRepHome(undefined), false);
  });

  it("goes back to the current home when a refreshed summary drops the flag", () => {
    const before = { id: "co-1", role: "member", repWorkspace: true };
    const refreshed = { id: "co-1", role: "member", repWorkspace: false };
    assert.equal(usesRepHome(before), true);
    assert.equal(usesRepHome(refreshed), false);
  });
});
