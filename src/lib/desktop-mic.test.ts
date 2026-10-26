import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { findChosen, isUnusual, micDevices } from "./desktop-mic.ts";

const input = (deviceId: string, label: string, groupId = deviceId) => ({ kind: "audioinput", deviceId, label, groupId }) as MediaDeviceInfo;

describe("micDevices", () => {
  it("lists the mics without the system's own entries, and names the default by its device", () => {
    const listed = micDevices([
      input("default", "Default - AirPods Pro (Bluetooth)", "g-air"),
      input("communications", "Communications - AirPods Pro (Bluetooth)", "g-air"),
      input("a1", "AirPods Pro (Bluetooth)", "g-air"),
      input("m1", "MacBook Pro Microphone (Built-in)", "g-mac"),
      { kind: "audiooutput", deviceId: "o1", label: "AirPods Pro", groupId: "g-air" } as MediaDeviceInfo,
    ]);
    assert.deepEqual(listed.devices, [
      { id: "a1", label: "AirPods Pro (Bluetooth)" },
      { id: "m1", label: "MacBook Pro Microphone (Built-in)" },
    ]);
    assert.equal(listed.defaultLabel, "AirPods Pro (Bluetooth)");
  });

  it("lists nothing before the page may use the mic (the names are hidden)", () => {
    assert.deepEqual(micDevices([input("default", ""), input("a1", "")]), { devices: [], defaultLabel: null });
  });

  it("falls back to the default entry's own name when no mic shares its group", () => {
    assert.equal(micDevices([input("default", "Default - USB Mic", "g-x"), input("u1", "USB Mic", "g-y")]).defaultLabel, "USB Mic");
  });
});

describe("findChosen", () => {
  const devices = [{ id: "a1", label: "AirPods Pro" }, { id: "m1", label: "MacBook Pro Microphone" }];

  it("finds the picked mic by id, else by name", () => {
    assert.deepEqual(findChosen(devices, { id: "a1", label: "AirPods Pro" }), devices[0]);
    assert.deepEqual(findChosen(devices, { id: "old", label: "MacBook Pro Microphone" }), devices[1]);
  });

  it("is null when nothing was picked or the picked mic is not connected", () => {
    assert.equal(findChosen(devices, null), null);
    assert.equal(findChosen(devices, { id: "i1", label: "iPhone" }), null);
  });
});

describe("isUnusual", () => {
  it("says so when the picked mic is missing", () => {
    assert.equal(isUnusual("iPhone", { id: "a1", label: "AirPods Pro" }, null, "AirPods Pro"), true);
    assert.equal(isUnusual("AirPods Pro", { id: "a1", label: "AirPods Pro" }, { id: "a1", label: "AirPods Pro" }, null), false);
  });

  it("without a pick, says so only when the mic differs from the last one that heard the rep", () => {
    assert.equal(isUnusual("iPhone", null, null, "AirPods Pro"), true);
    assert.equal(isUnusual("AirPods Pro", null, null, "AirPods Pro"), false);
    assert.equal(isUnusual("AirPods Pro", null, null, null), false);
  });
});
