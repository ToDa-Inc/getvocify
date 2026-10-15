import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  SETTINGS_TABS,
  firstAllowedSettingsPath,
  isSettingsPathAllowed,
  visibleSettingsTabs,
} from "./settings-nav.ts";

describe("visibleSettingsTabs", () => {
  it("gives the Head of Sales every tab", () => {
    assert.deepEqual(
      visibleSettingsTabs(true).map((t) => t.id),
      ["preferences", "calling", "agents", "usage", "crm", "offer", "team", "billing"],
    );
  });

  it("keeps the spec's order: mine first, then the company's", () => {
    assert.deepEqual(
      SETTINGS_TABS.map((t) => t.id),
      ["preferences", "calling", "calendar", "agents", "system", "usage", "crm", "offer", "team", "billing"],
    );
    const groups = SETTINGS_TABS.map((t) => t.group);
    assert.deepEqual(groups, [...groups].sort((a, b) => (a === b ? 0 : a === "personal" ? -1 : 1)));
  });

  it("has no playbooks tab: the editor lives in Proceso de venta", () => {
    const ids: string[] = SETTINGS_TABS.map((t) => t.id);
    assert.equal(ids.includes("playbooks"), false);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/playbooks", true), false);
  });

  it("has no language or theme tab: they live in the avatar menu", () => {
    const ids: string[] = SETTINGS_TABS.map((t) => t.id);
    assert.equal(ids.includes("language"), false);
    assert.equal(ids.includes("theme"), false);
  });

  it("has no transcription or brief tab: they are inside Preferences", () => {
    const ids: string[] = SETTINGS_TABS.map((t) => t.id);
    assert.equal(ids.includes("transcription"), false);
    assert.equal(ids.includes("brief"), false);
  });

  it("gives a rep only the personal tabs", () => {
    assert.deepEqual(
      visibleSettingsTabs(false).map((t) => t.id),
      ["preferences", "calling", "agents", "usage"],
    );
    assert.equal(visibleSettingsTabs(false).every((t) => t.group === "personal"), true);
  });
});

describe("firstAllowedSettingsPath", () => {
  it("is Preferences for everyone", () => {
    assert.equal(firstAllowedSettingsPath(true), "/dashboard/settings/preferences");
    assert.equal(firstAllowedSettingsPath(false), "/dashboard/settings/preferences");
  });
});

describe("isSettingsPathAllowed", () => {
  it("lets the Head of Sales onto every tab, flagged ones aside", () => {
    for (const tab of SETTINGS_TABS) {
      assert.equal(isSettingsPathAllowed(tab.to, true), !tab.flag && !tab.desktopOnly, tab.id);
    }
  });

  it("blocks a rep from company-wide tabs by direct URL", () => {
    for (const path of ["crm", "team", "billing", "offer"]) {
      assert.equal(isSettingsPathAllowed(`/dashboard/settings/${path}`, false), false, path);
    }
    assert.equal(isSettingsPathAllowed("/dashboard/settings", false), false);
  });

  it("lets a rep onto their personal tabs, including nested paths", () => {
    assert.equal(isSettingsPathAllowed("/dashboard/settings/preferences", false), true);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/calling", false), true);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/usage/anything", false), true);
  });

  it("lets the Head of Sales into a CRM's own page, not a sibling by prefix", () => {
    assert.equal(isSettingsPathAllowed("/dashboard/settings/crm/hubspot", true), true);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/whatever", true), false);
  });
});

describe("the Calendar tab", () => {
  it("shows for every role only while the meeting bot flag is on", () => {
    for (const isManager of [true, false]) {
      assert.equal(visibleSettingsTabs(isManager).some((t) => t.id === "calendar"), false);
      assert.equal(visibleSettingsTabs(isManager, ["RECALL_BOT_ENABLED"]).some((t) => t.id === "calendar"), true);
      assert.equal(isSettingsPathAllowed("/dashboard/settings/calendar", isManager), false);
      assert.equal(isSettingsPathAllowed("/dashboard/settings/calendar", isManager, ["RECALL_BOT_ENABLED"]), true);
    }
  });
});

describe("System tab", () => {
  it("shows only inside the desktop app, to managers and reps alike", () => {
    for (const isManager of [true, false]) {
      assert.equal(visibleSettingsTabs(isManager).some((t) => t.id === "system"), false);
      assert.equal(visibleSettingsTabs(isManager, [], { desktop: true }).some((t) => t.id === "system"), true);
      assert.equal(isSettingsPathAllowed("/dashboard/settings/system", isManager), false);
      assert.equal(isSettingsPathAllowed("/dashboard/settings/system", isManager, [], { desktop: true }), true);
    }
  });
});
