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
      ["crm", "calling", "offer", "transcription", "brief", "team", "usage", "billing"],
    );
  });

  it("keeps the spec's order", () => {
    assert.deepEqual(
      SETTINGS_TABS.map((t) => t.id),
      ["crm", "calling", "calendar", "offer", "transcription", "brief", "team", "usage", "billing", "system"],
    );
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

  it("shows Calling and Usage to the Head of Sales: they set their own call languages", () => {
    const ids = visibleSettingsTabs(true).map((t) => t.id);
    assert.equal(ids.includes("calling"), true);
    assert.equal(ids.includes("usage"), true);
  });

  it("gives a rep only the personal tabs", () => {
    assert.deepEqual(
      visibleSettingsTabs(false).map((t) => t.id),
      ["calling", "transcription", "usage"],
    );
  });
});

describe("firstAllowedSettingsPath", () => {
  it("is the CRM tab for the Head of Sales", () => {
    assert.equal(firstAllowedSettingsPath(true), "/dashboard/settings");
  });

  it("is Calling for a rep", () => {
    assert.equal(firstAllowedSettingsPath(false), "/dashboard/settings/calling");
  });
});

describe("isSettingsPathAllowed", () => {
  it("lets the Head of Sales onto every tab, flagged ones aside", () => {
    for (const tab of SETTINGS_TABS) {
      assert.equal(isSettingsPathAllowed(tab.to, true), !tab.flag && !tab.desktopOnly, tab.id);
    }
    assert.equal(isSettingsPathAllowed("/dashboard/settings/calling", true), true);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/usage", true), true);
  });

  it("blocks a rep from company-wide tabs by direct URL", () => {
    assert.equal(isSettingsPathAllowed("/dashboard/settings", false), false);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/team", false), false);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/billing", false), false);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/offer", false), false);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/brief", false), false);
  });

  it("lets a rep onto their personal tabs, including nested paths", () => {
    assert.equal(isSettingsPathAllowed("/dashboard/settings/calling", false), true);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/transcription", false), true);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/usage", false), true);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/usage/anything", false), true);
  });

  it("does not let the CRM index match a sibling path by prefix", () => {
    assert.equal(isSettingsPathAllowed("/dashboard/settings/transcription", true), true);
    // The index tab uses exact match, so it never swallows a sibling route.
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
