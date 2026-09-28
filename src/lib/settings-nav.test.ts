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
    assert.deepEqual(visibleSettingsTabs(true), [...SETTINGS_TABS]);
  });

  it("gives a rep only the personal tabs", () => {
    assert.deepEqual(
      visibleSettingsTabs(false).map((t) => t.id),
      ["calling", "glossary", "usage"],
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
  it("lets the Head of Sales onto every company-wide tab", () => {
    for (const tab of SETTINGS_TABS) {
      assert.equal(isSettingsPathAllowed(tab.to, true), true);
    }
  });

  it("blocks a rep from company-wide tabs by direct URL", () => {
    assert.equal(isSettingsPathAllowed("/dashboard/settings", false), false);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/team", false), false);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/billing", false), false);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/offer", false), false);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/playbooks", false), false);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/brief", false), false);
  });

  it("lets a rep onto their personal tabs, including nested paths", () => {
    assert.equal(isSettingsPathAllowed("/dashboard/settings/calling", false), true);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/glossary", false), true);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/usage", false), true);
    assert.equal(isSettingsPathAllowed("/dashboard/settings/usage/anything", false), true);
  });

  it("does not let the CRM index match a rep's calling path by prefix", () => {
    assert.equal(isSettingsPathAllowed("/dashboard/settings/calling", true), true);
    // The index tab uses exact match, so it never swallows a sibling route.
    assert.equal(isSettingsPathAllowed("/dashboard/settings/whatever", true), false);
  });
});
