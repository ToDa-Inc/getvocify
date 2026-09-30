import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { isManagerRole, navItemsFor, topBarActions, usesRepHome, type NavItem } from "./nav.ts";

const home: NavItem = { id: "home", labelKey: "navHome", path: "/dashboard" };
const interactions: NavItem = { id: "interactions", labelKey: "navInteractions", path: "/dashboard/interactions" };
const insights: NavItem = { id: "insights", labelKey: "navInsights", path: "/dashboard/insights" };
const coach: NavItem = { id: "coach", labelKey: "navCoach", path: "/dashboard/coach" };
const settings: NavItem = { id: "settings", labelKey: "navSettings", path: "/dashboard/settings" };

describe("navItemsFor for a rep", () => {
  it("gives a member Inicio, Interacciones, Coaching and Ajustes, with plans, when the workspace is off", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: false }), {
      items: [home, interactions, coach, settings],
      showPlans: true,
    });
  });

  it("gives a member the same four places, without plans, in the workspace (Inicio, never Hoy)", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: true }), {
      items: [home, interactions, coach, settings],
      showPlans: false,
    });
  });

  it("no longer adds a Playbook item: the rep's playbook is a tab of Coaching", () => {
    for (const repWorkspace of [false, true]) {
      assert.deepEqual(
        navItemsFor({ role: "member", repWorkspace, playbookTabEnabled: true }),
        navItemsFor({ role: "member", repWorkspace }),
      );
    }
  });

  it("treats a missing or unknown role like a member", () => {
    assert.deepEqual(navItemsFor({}), navItemsFor({ role: "member", repWorkspace: false }));
    assert.deepEqual(navItemsFor({ role: null }), navItemsFor({ role: "member", repWorkspace: false }));
    assert.deepEqual(navItemsFor({ role: "viewer", repWorkspace: true }), navItemsFor({ role: "member", repWorkspace: true }));
  });
});

describe("navItemsFor for the Head of Sales", () => {
  it("is Inicio, Interacciones, Equipo and Ajustes, whatever the flags", () => {
    for (const role of ["owner", "admin"]) {
      for (const repWorkspace of [false, true]) {
        for (const playbookTabEnabled of [false, true]) {
          assert.deepEqual(navItemsFor({ role, repWorkspace, playbookTabEnabled }), {
            items: [home, interactions, insights, settings],
            showPlans: role === "owner",
          });
        }
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
