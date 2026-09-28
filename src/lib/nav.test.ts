import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { isManagerRole, managerTopBarAsk, navItemsFor, topBarActions, usesRepHome, type NavItem } from "./nav.ts";

const home: NavItem = { id: "home", labelKey: "navHome", path: "/dashboard" };
const memos: NavItem = { id: "memos", labelKey: "navMemos", path: "/dashboard/memos" };
const copilot: NavItem = { id: "copilot", labelKey: "navCopilot", path: "/dashboard/copilot", beta: true };
const ask: NavItem = { id: "ask", labelKey: "navAsk", path: "/dashboard/ask" };
const call: NavItem = { id: "call", labelKey: "navCall" };
const insights: NavItem = { id: "insights", labelKey: "navInsights", path: "/dashboard/insights" };
const coach: NavItem = { id: "coach", labelKey: "navCoach", path: "/dashboard/coach" };
const playbook: NavItem = { id: "playbook", labelKey: "navPlaybook", path: "/dashboard/playbook" };
const settings: NavItem = { id: "settings", labelKey: "navSettings", path: "/dashboard/settings" };

const today: NavItem = { ...home, labelKey: "navToday" };
const conversations: NavItem = { ...memos, labelKey: "navConversations" };
const recordings: NavItem = { ...memos, labelKey: "navRecordings" };

describe("navItemsFor for a rep (Lista 4 E1–E5)", () => {
  it("gives a member Home, Recordings, Coach and Settings, with plans, when the workspace is off", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: false }), {
      items: [home, recordings, coach, settings],
      showPlans: true,
    });
  });

  it("gives a member Today, Recordings, Coach and Settings without plans in the workspace", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: true }), {
      items: [today, recordings, coach, settings],
      showPlans: false,
    });
  });

  it("adds Playbook after Recordings when enabled", () => {
    assert.deepEqual(
      navItemsFor({ role: "member", repWorkspace: true, playbookTabEnabled: true }).items,
      [today, recordings, playbook, coach, settings],
    );
  });

  it("never lists Copilot, Ask, Call or Team for a rep (Ask and Call live in the top bar)", () => {
    for (const repWorkspace of [false, true]) {
      const ids: string[] = navItemsFor({ role: "member", repWorkspace }).items.map((item) => item.id);
      for (const gone of ["copilot", "ask", "call", "insights"]) assert.equal(ids.includes(gone), false, gone);
    }
  });

  it("treats a missing or unknown role like a member", () => {
    assert.deepEqual(navItemsFor({}), navItemsFor({ role: "member", repWorkspace: false }));
    assert.deepEqual(navItemsFor({ role: null }), navItemsFor({ role: "member", repWorkspace: false }));
    assert.deepEqual(navItemsFor({ role: "viewer", repWorkspace: true }), navItemsFor({ role: "member", repWorkspace: true }));
  });
});

const summary: NavItem = { ...home, labelKey: "navSummary" };
const process: NavItem = { id: "process", labelKey: "navProcess", path: "/dashboard/process" };

describe("navItemsFor for the Head of Sales (HEAD_OF_SALES_DASHBOARD_PLAN §2)", () => {
  it("is Resumen, Equipo, Proceso de venta and Ajustes, whatever the flags", () => {
    for (const role of ["owner", "admin"]) {
      for (const repWorkspace of [false, true]) {
        for (const playbookTabEnabled of [false, true]) {
          assert.deepEqual(navItemsFor({ role, repWorkspace, playbookTabEnabled }), {
            items: [summary, insights, process, settings],
            showPlans: true,
          });
        }
      }
    }
  });

  it("never links the rep places: Today, recordings, Copilot, Call, Coach", () => {
    const ids: string[] = navItemsFor({ role: "owner", repWorkspace: true, playbookTabEnabled: true }).items.map((i) => i.id);
    for (const gone of ["memos", "copilot", "ask", "call", "coach", "playbook"]) assert.equal(ids.includes(gone), false, gone);
  });
});

describe("topBarActions", () => {
  it("puts Ask and Call in the top bar for reps only", () => {
    assert.equal(topBarActions("member"), true);
    assert.equal(topBarActions(null), true);
    assert.equal(topBarActions("owner"), false);
    assert.equal(topBarActions("admin"), false);
  });

  it("gives the Head of Sales Ask (without Call) in the top bar", () => {
    assert.equal(managerTopBarAsk("owner"), true);
    assert.equal(managerTopBarAsk("admin"), true);
    assert.equal(managerTopBarAsk("member"), false);
    assert.equal(managerTopBarAsk(null), false);
  });
});

describe("isManagerRole / usesRepHome", () => {
  it("only owner and admin manage", () => {
    assert.equal(isManagerRole("owner"), true);
    assert.equal(isManagerRole("admin"), true);
    assert.equal(isManagerRole("member"), false);
    assert.equal(isManagerRole(null), false);
  });

  it("uses the rep home only when the workspace flag is on", () => {
    assert.equal(usesRepHome({ repWorkspace: true }), true);
    assert.equal(usesRepHome({ repWorkspace: false }), false);
    assert.equal(usesRepHome(null), false);
  });
});
