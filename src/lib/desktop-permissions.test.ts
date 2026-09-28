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
  it("requires both channels", () => {
    assert.equal(
      desktopPermissionsReady({ platform: "darwin", microphone: "authorized", systemAudio: "never_requested" }),
      false,
    );
    assert.equal(
      desktopPermissionsReady({ platform: "darwin", microphone: "authorized", systemAudio: "authorized", signing: "signed" }),
      true,
    );
    assert.equal(
      desktopPermissionsReady({ platform: "darwin", microphone: "authorized", systemAudio: "authorized", signing: "adhoc" }),
      false,
    );
  });
});

describe("desktopPermissionsBlocker", () => {
  it("prioritises signing over permissions", () => {
    assert.equal(
      desktopPermissionsBlocker({ platform: "darwin", microphone: "never_requested", systemAudio: "never_requested", signing: "adhoc" }),
      "signing",
    );
  });
});
