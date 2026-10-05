import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  desktopPermissionsBlocker,
  desktopPermissionsReady,
  normalizePermissionStatus,
  permissionAction,
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
