import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  crmTabsToAsk,
  desktopPermissionsBlocker,
  desktopPermissionsReady,
  normalizeCrmTabsStatus,
  normalizePermissionStatus,
  permissionAction,
  permissionCopy,
  systemAudioHint,
} from "./desktop-permissions.ts";

describe("normalizePermissionStatus", () => {
  it("maps platform strings", () => {
    assert.equal(normalizePermissionStatus("authorized"), "authorized");
    assert.equal(normalizePermissionStatus("granted"), "authorized");
    assert.equal(normalizePermissionStatus("denied"), "denied");
    assert.equal(normalizePermissionStatus(undefined), "never_requested");
  });
});

describe("permissionAction", () => {
  it("opens settings when denied", () => {
    assert.equal(permissionAction("denied"), "open_settings");
    assert.equal(permissionAction("never_requested"), "request");
    assert.equal(permissionAction("authorized"), "none");
  });
});

describe("desktopPermissionsReady", () => {
  it("requires both channels on macOS", () => {
    assert.equal(
      desktopPermissionsReady({ platform: "darwin", microphone: "authorized", systemAudio: "never_requested" }),
      false,
    );
    assert.equal(
      desktopPermissionsReady({ platform: "darwin", microphone: "authorized", systemAudio: "authorized" }),
      true,
    );
  });

  it("requires only microphone on Windows", () => {
    assert.equal(
      desktopPermissionsReady({ platform: "win32", microphone: "authorized", systemAudio: "never_requested" }),
      true,
    );
    assert.equal(
      desktopPermissionsReady({ platform: "win32", microphone: "authorized", systemAudio: "authorized" }),
      true,
    );
    assert.equal(
      desktopPermissionsReady({ platform: "win32", microphone: "never_requested", systemAudio: "authorized" }),
      false,
    );
  });
});

describe("desktopPermissionsBlocker", () => {
  it("blocks until both channels are ready on macOS", () => {
    assert.equal(
      desktopPermissionsBlocker({ platform: "darwin", microphone: "never_requested", systemAudio: "never_requested" }),
      "permissions",
    );
    assert.equal(
      desktopPermissionsBlocker({ platform: "darwin", microphone: "authorized", systemAudio: "authorized" }),
      "none",
    );
  });

  it("blocks until microphone is ready on Windows", () => {
    assert.equal(
      desktopPermissionsBlocker({ platform: "win32", microphone: "never_requested", systemAudio: "authorized" }),
      "permissions",
    );
    assert.equal(
      desktopPermissionsBlocker({ platform: "win32", microphone: "authorized", systemAudio: "authorized" }),
      "none",
    );
  });
});

describe("systemAudioHint", () => {
  it("asks for a relaunch after Settings, then points at re-adding the app", () => {
    assert.equal(systemAudioHint("never_requested", { asked: false, relaunched: false }), "none");
    assert.equal(systemAudioHint("never_requested", { asked: true, relaunched: false }), "relaunch");
    assert.equal(systemAudioHint("never_requested", { asked: false, relaunched: true }), "stuck");
    assert.equal(systemAudioHint("authorized", { asked: true, relaunched: true }), "none");
  });
});

describe("CRM tab permission", () => {
  const base = { platform: "darwin", microphone: "authorized", systemAudio: "authorized" } as const;

  it("never blocks recording", () => {
    assert.equal(desktopPermissionsReady({ ...base, crmTabs: "denied" }), true);
  });

  it("is still to ask only when the Mac reports it and the rep has not answered", () => {
    assert.equal(crmTabsToAsk({ ...base, crmTabs: "never_requested" }), true);
    assert.equal(crmTabsToAsk({ ...base, crmTabs: "unavailable" }), true);
    assert.equal(crmTabsToAsk({ ...base, crmTabs: "authorized" }), false);
    assert.equal(crmTabsToAsk({ ...base, crmTabs: "denied" }), false);
    assert.equal(crmTabsToAsk(base), false);
  });

  it("reads the Mac's answer, keeping 'no browser open' apart", () => {
    assert.equal(normalizeCrmTabsStatus("authorized"), "authorized");
    assert.equal(normalizeCrmTabsStatus("not_asked"), "never_requested");
    assert.equal(normalizeCrmTabsStatus("unavailable"), "unavailable");
    assert.equal(normalizeCrmTabsStatus(undefined), undefined);
  });

  it("says what it is for", () => {
    assert.equal(permissionCopy("crmTabs").enableLabel, "Read your CRM tab");
    assert.equal(permissionCopy("crmTabs").enableBody, "So Vocify can call the contact you have open.");
  });
});
