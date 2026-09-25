import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ingestSuggestSseEvents, parseSuggestSseStream } from "./suggest-stream.js";
import { reduceSuggestion } from "./suggestion-state.js";

describe("suggest SSE stream (beta contract)", () => {
  it("parses token and legacy result events from split chunks", () => {
    let buffer = "";
    buffer = parseSuggestSseStream(buffer, 'data: {"type":"token","text":"Hi"}\n\n', () => {});
    const types = [];
    buffer = parseSuggestSseStream(
      buffer,
      'data: {"type":"result","suggestion":{"say_this":"Ok"}}\n\n',
      (event) => types.push(event.type),
    );
    assert.deepEqual(types, ["result"]);
    const split = ingestSuggestSseEvents("", 'data: {"type":"done"}\n');
    assert.equal(split.events.length, 0);
    const closed = ingestSuggestSseEvents(split.buffer, "\n");
    assert.equal(closed.events.length, 1);
  });

  it("drops stale results after meeting switch (cancel contract)", () => {
    let state = reduceSuggestion({ meetingId: null, requestId: null, card: null }, { type: "start", meetingId: "meet-1" });
    state = reduceSuggestion(state, { type: "request", meetingId: "meet-1", requestId: "sug-1" });
    state = reduceSuggestion(state, { type: "switch", meetingId: "meet-2" });
    const stale = reduceSuggestion(state, {
      type: "result",
      meetingId: "meet-1",
      requestId: "sug-1",
      card: { text: "vieja" },
    });
    assert.equal(stale.card, null);
    assert.equal(stale.meetingId, "meet-2");
  });
});
