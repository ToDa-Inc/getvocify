import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { isManagerRole, isNavActive, navItemsFor, usesRepHome, type NavItem } from "./nav.ts";

const home: NavItem = { id: "home", labelKey: "navHome", path: "/dashboard" };
const insights: NavItem = { id: "insights", labelKey: "navInsights", path: "/dashboard/insights" };
const coach: NavItem = { id: "coach", labelKey: "navCoach", path: "/dashboard/coach" };
const playbook: NavItem = { id: "playbook", labelKey: "navPlaybook", path: "/dashboard/playbook" };
const process: NavItem = { id: "process", labelKey: "navProcess", path: "/dashboard/process" };
const settings: NavItem = { id: "settings", labelKey: "navSettings", path: "/dashboard/settings" };

describe("navItemsFor for a member (Llamadas, Reuniones, General)", () => {
  it("gives Inicio, Playbook, Coaching and Ajustes, with plans, when the workspace is off", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: false, playbookTabEnabled: true }), {
      items: [home, playbook, coach, settings],
      showPlans: true,
    });
  });

  it("gives the same places, without plans, in the workspace (Inicio replaces Hoy)", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: true, playbookTabEnabled: true }), {
      items: [home, playbook, coach, settings],
      showPlans: false,
    });
  });

  it("drops Playbook only when the tab is off", () => {
    assert.deepEqual(navItemsFor({ role: "member", repWorkspace: true }).items, [home, coach, settings]);
  });

  it("never gives a member Equipo, Proceso de venta or Interacciones (it is Inicio's list)", () => {
    const ids: string[] = navItemsFor({ role: "member", repWorkspace: true, playbookTabEnabled: true }).items.map((item) => item.id);
    for (const id of ["insights", "process", "interactions"]) assert.equal(ids.includes(id), false);
  });

  it("treats a missing or unknown role like a member", () => {
    assert.deepEqual(navItemsFor({}), navItemsFor({ role: "member", repWorkspace: false }));
    assert.deepEqual(navItemsFor({ role: null }), navItemsFor({ role: "member", repWorkspace: false }));
    assert.deepEqual(navItemsFor({ role: "viewer", repWorkspace: true }), navItemsFor({ role: "member", repWorkspace: true }));
  });
});

describe("navItemsFor for the Admin/Owner", () => {
  it("adds Inicio to Equipo, Proceso de venta and Ajustes, whatever the flags", () => {
    for (const role of ["owner", "admin"]) {
      for (const repWorkspace of [false, true]) {
        for (const playbookTabEnabled of [false, true]) {
          assert.deepEqual(navItemsFor({ role, repWorkspace, playbookTabEnabled }), {
            items: [home, insights, process, settings],
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
  it("lights Inicio on /dashboard and on what it opens (Hoy, Interacciones, a memo), nowhere else", () => {
    assert.equal(isNavActive("/dashboard", home), true);
    assert.equal(isNavActive("/dashboard/today", home), true);
    assert.equal(isNavActive("/dashboard/interactions", home), true);
    assert.equal(isNavActive("/dashboard/memos/abc", home), true);
    assert.equal(isNavActive("/dashboard/insights", home), false);
    assert.equal(isNavActive("/dashboard/settings", home), false);
  });

  it("lights an item on its own path and below it, not on a path that only shares a prefix", () => {
    assert.equal(isNavActive("/dashboard/insights/rep/u1", insights), true);
    assert.equal(isNavActive("/dashboard/playbook", playbook), true);
    assert.equal(isNavActive("/dashboard/playbooks", playbook), false);
  });
});
