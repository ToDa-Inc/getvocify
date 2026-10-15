import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { byChannel, channelGroups, channelsOf, channelTypeOptions, otherChannel, railChannels, ruleChannelsOf } from "./type-channels.ts";

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

describe("railChannels", () => {
  it("reads the type's own channels when the company goes by channel", () => {
    const payload = { details: { a: { channels: ["meeting"], applies_to: { channels: ["call"] } } } };
    assert.deepEqual(railChannels(payload, "a"), ["meeting"]);
  });

  it("falls back to the rule's channels, a visit counting as a meeting", () => {
    const payload = { details: { cold: { applies_to: { channels: ["call"] } }, ae: { applies_to: { channels: ["meeting", "visit", "call"] } }, visit: { applies_to: { channels: ["visit"] } } } };
    assert.deepEqual(railChannels(payload, "cold"), ["call"]);
    assert.deepEqual(railChannels(payload, "ae"), ["call", "meeting"]);
    assert.deepEqual(railChannels(payload, "visit"), ["meeting"]);
  });

  it("is both for a type with no channel information", () => {
    assert.deepEqual(railChannels({ details: { x: {} } }, "x"), ["call", "meeting"]);
    assert.deepEqual(railChannels(null, "x"), ["call", "meeting"]);
  });

  it("maps a tab back to the rule channels it covers", () => {
    assert.deepEqual(ruleChannelsOf("call"), ["call"]);
    assert.deepEqual(ruleChannelsOf("meeting"), ["meeting", "visit"]);
  });
});
