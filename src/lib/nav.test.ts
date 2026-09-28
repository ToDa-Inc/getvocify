import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { isManagerRole, navItemsFor, usesRepHome, type NavItem } from "./nav.ts";

const home: NavItem = { id: "home", labelKey: "navHome", path: "/dashboard" };
const memos: NavItem = { id: "memos", labelKey: "navMemos", path: "/dashboard/memos" };
const insights: NavItem = { id: "insights", labelKey: "navInsights", path: "/dashboard/insights" };
const coach: NavItem = { id: "coach", labelKey: "navCoach", path: "/dashboard/coach" };
const playbook: NavItem = { id: "playbook", labelKey: "navPlaybook", path: "/dashboard/playbook" };
const settings: NavItem = { id: "settings", labelKey: "navSettings", path: "/dashboard/settings" };

const today: NavItem = { ...home, labelKey: "navToday" };
const conversations: NavItem = { ...memos, labelKey: "navConversations" };

describe("navItemsFor with the rep workspace off", () => {
  it("gives a member Home, Recordings, Coach and Settings, with the plans card", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: false }), {
      items: [home, memos, coach, settings],
      showPlans: true,
    });
  });

  it("gives owners and admins Team instead of Coach", () => {
    for (const role of ["owner", "admin"]) {
      assert.deepEqual(navItemsFor({ role, repWorkspace: false }), {
        items: [home, memos, insights, settings],
        showPlans: true,
      });
    }
  });

  it("treats a missing flag or role like a member with the workspace off", () => {
    assert.deepEqual(navItemsFor({ role: "member" }), navItemsFor({ role: "member", repWorkspace: false }));
    assert.deepEqual(navItemsFor({ role: null }), navItemsFor({ role: "member", repWorkspace: false }));
    assert.deepEqual(navItemsFor({}), navItemsFor({ role: "member", repWorkspace: false }));
  });
});

describe("navItemsFor with the rep workspace on", () => {
  it("gives a member Today, Recordings, Coach and Settings without plans", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: true }), {
      items: [today, conversations, coach, settings],
      showPlans: false,
    });
  });

  it("gives owners and admins Team instead of Coach, and plans", () => {
    for (const role of ["owner", "admin"]) {
      assert.deepEqual(navItemsFor({ role, repWorkspace: true }), {
        items: [today, conversations, insights, settings],
        showPlans: true,
      });
    }
  });

  it("keeps every shared entry on the same route in both workspaces", () => {
    for (const role of ["member", "owner"]) {
      const before = new Map(navItemsFor({ role }).items.map((item) => [item.id, item.path]));
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

describe("navItemsFor leaves Copilot, Ask and Call out of the sidebar", () => {
  it("never lists them for any role or workspace (Ask and Call live in the top bar)", () => {
    for (const role of ["member", "admin", "owner", null]) {
      for (const repWorkspace of [false, true]) {
        for (const playbookTabEnabled of [false, true]) {
          const ids: string[] = navItemsFor({ role, repWorkspace, playbookTabEnabled }).items.map((item) => item.id);
          for (const gone of ["copilot", "ask", "call"]) assert.equal(ids.includes(gone), false, gone);
        }
      }
    }
  });

  it("gives Team only to managers and Coach only to reps", () => {
    for (const repWorkspace of [false, true]) {
      const member = navItemsFor({ role: "member", repWorkspace }).items.map((item) => item.id);
      const owner = navItemsFor({ role: "owner", repWorkspace }).items.map((item) => item.id);
      assert.equal(member.includes("insights"), false);
      assert.equal(member.includes("coach"), true);
      assert.equal(owner.includes("insights"), true);
      assert.equal(owner.includes("coach"), false);
    }
  });
});

describe("navItemsFor with the Playbook tab flag", () => {
  it("is off by default for every role and workspace", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: false }).items, [home, memos, coach, settings]);
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: true }).items, [today, conversations, coach, settings]);
  });

  it("adds Playbook after Recordings for a member", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: false, playbookTabEnabled: true }), {
      items: [home, memos, playbook, coach, settings],
      showPlans: true,
    });
  });

  it("adds Playbook for owners and admins too, before Team", () => {
    assert.deepEqual(navItemsFor({ role: "owner", repWorkspace: false, playbookTabEnabled: true }), {
      items: [home, memos, playbook, insights, settings],
      showPlans: true,
    });
  });

  it("adds Playbook in the rep workspace for every role", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: true, playbookTabEnabled: true }).items, [
      today, conversations, playbook, coach, settings,
    ]);
    assert.deepEqual(navItemsFor({ role: "owner", repWorkspace: true, playbookTabEnabled: true }).items, [
      today, conversations, playbook, insights, settings,
    ]);
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
