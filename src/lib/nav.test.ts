import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { isManagerRole, isNavActive, navItemsFor, topBarActions, usesRepHome, type NavItem } from "./nav.ts";

const home: NavItem = { id: "home", labelKey: "navHome", path: "/dashboard" };
const insights: NavItem = { id: "insights", labelKey: "navInsights", path: "/dashboard/insights" };
const process: NavItem = { id: "process", labelKey: "navProcess", path: "/dashboard/process" };
const coach: NavItem = { id: "coach", labelKey: "navCoach", path: "/dashboard/coach" };
const settings: NavItem = { id: "settings", labelKey: "navSettings", path: "/dashboard/settings" };

describe("navItemsFor for a rep", () => {
  it("gives a member Inicio, Coaching and Ajustes, with plans, when the workspace is off", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: false }), {
      items: [home, coach, settings],
      showPlans: true,
    });
  });

  it("gives a member the same three places, without plans, in the workspace (Inicio, never Hoy)", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: true }), {
      items: [home, coach, settings],
      showPlans: false,
    });
  });

  it("has no Playbook or Interacciones item: the playbook is a tab of Coaching, interactions live in Inicio", () => {
    for (const repWorkspace of [false, true]) {
      const ids = navItemsFor({ role: "member", repWorkspace }).items.map((item) => item.id);
      assert.deepEqual(ids, ["home", "coach", "settings"]);
    }
  });

  it("treats a missing or unknown role like a member", () => {
    assert.deepEqual(navItemsFor({}), navItemsFor({ role: "member", repWorkspace: false }));
    assert.deepEqual(navItemsFor({ role: null }), navItemsFor({ role: "member", repWorkspace: false }));
    assert.deepEqual(navItemsFor({ role: "viewer", repWorkspace: true }), navItemsFor({ role: "member", repWorkspace: true }));
  });
});

describe("navItemsFor for the Head of Sales", () => {
  it("is Inicio, Equipo, Proceso de venta and Ajustes, whatever the flags", () => {
    for (const role of ["owner", "admin"]) {
      for (const repWorkspace of [false, true]) {
        assert.deepEqual(navItemsFor({ role, repWorkspace }), {
          items: [home, insights, process, settings],
          showPlans: role === "owner",
        });
      }
    }
  });

  it("shows the Plans card to the owner only (billing is the owner's)", () => {
    assert.equal(navItemsFor({ role: "owner" }).showPlans, true);
    assert.equal(navItemsFor({ role: "admin" }).showPlans, false);
  });
});

describe("topBarActions", () => {
  it("puts Llamar in the top bar for reps only", () => {
    assert.equal(topBarActions("member"), true);
    assert.equal(topBarActions(null), true);
    assert.equal(topBarActions("owner"), false);
    assert.equal(topBarActions("admin"), false);
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

describe("isNavActive", () => {
  it("lights Inicio on /dashboard and on what Inicio opens: the full Hoy, the interactions and a memo's detail", () => {
    assert.equal(isNavActive("/dashboard", home), true);
    assert.equal(isNavActive("/dashboard/today", home), true);
    assert.equal(isNavActive("/dashboard/interactions", home), true);
    assert.equal(isNavActive("/dashboard/interactions/anything", home), true);
    assert.equal(isNavActive("/dashboard/memos/123", home), true);
    assert.equal(isNavActive("/dashboard/coach", home), false);
    assert.equal(isNavActive("/dashboard/settings", home), false);
  });

  it("lights the other items on their path and below it, not on a longer sibling", () => {
    assert.equal(isNavActive("/dashboard/settings/team", settings), true);
    assert.equal(isNavActive("/dashboard/process", process), true);
    assert.equal(isNavActive("/dashboard/insights/rep/u1", insights), true);
    assert.equal(isNavActive("/dashboard/coach", coach), true);
    assert.equal(isNavActive("/dashboard/coaching", coach), false);
  });
});
