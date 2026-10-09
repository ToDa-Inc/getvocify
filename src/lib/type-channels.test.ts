import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { byChannel, channelGroups, channelsOf, channelTypeOptions, otherChannel } from "./type-channels.ts";

const PAYLOAD = {
  motions: { cold: "published", inbound_lead: "missing", demo: "draft", old: "paused", both: "published" },
  details: {
    cold: { channels: ["call"] },
    inbound_lead: { channels: ["call"] },
    demo: { channels: ["meeting"] },
    old: { channels: ["call"] },
    both: { channels: ["call", "meeting"] },
  },
  type_detection: { by_channel: true, call_reading: true },
};

const OPTIONS = [
  { key: "both", label: "Seguimiento", scored: true, status: "published" as const },
  { key: "cold", label: "Llamada en frío", scored: true, status: "published" as const },
  { key: "demo", label: "Demo", scored: true, status: "draft" as const },
  { key: "inbound_lead", label: "Lead inbound", scored: true, status: "missing" as const },
  { key: "old", label: "Vieja", scored: true, status: "paused" as const },
  { key: "internal", label: "Interna", scored: false },
];

describe("types by channel", () => {
  it("is on only when the server says how types are detected", () => {
    assert.equal(byChannel(PAYLOAD), true);
    assert.equal(byChannel({ motions: {} }), false);
    assert.equal(byChannel(undefined), false);
  });

  it("a type without channels belongs to both", () => {
    assert.deepEqual(channelsOf({ details: { x: { channels: [] } } }, "x"), ["call", "meeting"]);
    assert.deepEqual(channelsOf({}, "y"), ["call", "meeting"]);
  });

  it("offers the channel's types with or without a playbook, never a paused one, Interna last", () => {
    assert.deepEqual(channelTypeOptions(OPTIONS, PAYLOAD, "call").map((option) => option.key), ["both", "cold", "inbound_lead", "internal"]);
    assert.deepEqual(channelTypeOptions(OPTIONS, PAYLOAD, "meeting").map((option) => option.key), ["both", "demo", "internal"]);
  });

  it("a voice note or a visit has only Interna", () => {
    assert.deepEqual(channelTypeOptions(OPTIONS, PAYLOAD, "voice_note").map((option) => option.key), ["internal"]);
  });

  it("groups types under calls and meetings; a type of both is in both", () => {
    assert.deepEqual(channelGroups(["cold", "demo", "both"], PAYLOAD), { call: ["cold", "both"], meeting: ["demo", "both"] });
  });

  it("switching the channel goes to the other one", () => {
    assert.equal(otherChannel("call"), "meeting");
    assert.equal(otherChannel("meeting"), "call");
  });
});
