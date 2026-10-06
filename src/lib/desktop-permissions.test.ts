import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  desktopPermissionsBlocker,
  desktopPermissionsReady,
  normalizePermissionStatus,
  permissionAction,
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
  it("requires both channels", () => {
    assert.equal(
      desktopPermissionsReady({ platform: "darwin", microphone: "authorized", systemAudio: "never_requested" }),
      false,
    );
    assert.equal(
      desktopPermissionsReady({ platform: "darwin", microphone: "authorized", systemAudio: "authorized" }),
      true,
    );
  });
});

describe("desktopPermissionsBlocker", () => {
  it("blocks until both channels are ready", () => {
    assert.equal(
      desktopPermissionsBlocker({ platform: "darwin", microphone: "never_requested", systemAudio: "never_requested" }),
      "permissions",
    );
    assert.equal(
      desktopPermissionsBlocker({ platform: "darwin", microphone: "authorized", systemAudio: "authorized" }),
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
