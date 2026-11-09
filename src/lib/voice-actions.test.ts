import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { applyChannelResult, EMPTY_MEETING_TRANSCRIPT, applyVoice, meetingDisplayTurns } from "./meeting-transcript.ts";
import { applyVoiceAction, parseVoiceCommand, voiceMessage } from "./voice-actions.ts";

describe("parseVoiceCommand", () => {
  it("reads the three actions the island sends", () => {
    assert.deepEqual(parseVoiceCommand('voice:{"op":"rename","voice":2,"name":"  Laura "}'), { op: "rename", voice: 2, name: "Laura" });
    assert.deepEqual(parseVoiceCommand('voice:{"op":"merge","keep":1,"drop":3}'), { op: "merge", keep: 1, drop: 3 });
    assert.deepEqual(parseVoiceCommand('voice:{"op":"move","starts":[3,4.5],"voice":null}'), { op: "move", starts: [3, 4.5], voice: null });
    assert.deepEqual(parseVoiceCommand('voice:{"op":"move","starts":[3],"voice":2}'), { op: "move", starts: [3], voice: 2 });
  });

  it("drops anything else, including a command that is not a voice one", () => {
    for (const bad of [
      "stop",
      "voice:",
      "voice:not json",
      "voice:null",
      'voice:{"op":"rename","voice":0,"name":"x"}',
      'voice:{"op":"rename","voice":2}',
      'voice:{"op":"merge","keep":2,"drop":2}',
      'voice:{"op":"merge","keep":"1","drop":2}',
      'voice:{"op":"move","starts":[],"voice":1}',
      'voice:{"op":"move","starts":["a"],"voice":1}',
      'voice:{"op":"move","starts":[1],"voice":1.5}',
      'voice:{"op":"delete"}',
    ]) {
      assert.equal(parseVoiceCommand(bad), null, bad);
    }
  });

  it("cuts a name that is too long", () => {
    const action = parseVoiceCommand(`voice:${JSON.stringify({ op: "rename", voice: 1, name: "a".repeat(200) })}`);
    assert.equal(action?.op === "rename" && action.name.length, 60);
  });
});

describe("applyVoiceAction and voiceMessage", () => {
  const meeting = () => {
    let state = EMPTY_MEETING_TRANSCRIPT;
    for (const [text, start, voice] of [["Hola.", 0, 1], ["Buenas.", 3, 2]] as const) {
      state = applyVoice(applyChannelResult(state, { text, isFinal: true, audioChannel: "prospect", start, end: start + 2 }), start, voice);
    }
    return state;
  };

  it("renames, merges and moves at once, except a move to a voice the backend has yet to name", () => {
    const labels = (state: ReturnType<typeof meeting>) => meetingDisplayTurns(state).map((t) => t.label);
    assert.deepEqual(labels(applyVoiceAction(meeting(), { op: "rename", voice: 2, name: "Luis" })), ["Voice 1", "Luis"]);
    assert.deepEqual(labels(applyVoiceAction(meeting(), { op: "merge", keep: 1, drop: 2 })), ["Them"]);
    assert.deepEqual(labels(applyVoiceAction(meeting(), { op: "move", starts: [3], voice: 1 })), ["Them"]);
    const state = meeting();
    assert.equal(applyVoiceAction(state, { op: "move", starts: [3], voice: null }), state);
  });

  it("tells the backend about merges and moves, not about names", () => {
    assert.deepEqual(voiceMessage({ op: "merge", keep: 1, drop: 2 }), { type: "VoiceMerge", keep: 1, drop: 2 });
    assert.deepEqual(voiceMessage({ op: "move", starts: [3, 4], voice: null }), { type: "VoiceMove", starts: [3, 4], voice: null });
    assert.equal(voiceMessage({ op: "rename", voice: 1, name: "Ana" }), null);
  });
});
