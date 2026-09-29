import assert from "node:assert/strict";
import test from "node:test";
import { parseSse } from "./ask-sse.ts";

test("parses whole events and keeps the unfinished tail", () => {
  const first = parseSse('data: {"type":"turn","turn_id":"t1"}\n\ndata: {"type":"con');
  assert.deepEqual(first.events, [{ type: "turn", turn_id: "t1" }]);
  const second = parseSse(first.rest + 'tent","delta":"Hola"}\n\n');
  assert.deepEqual(second.events, [{ type: "content", delta: "Hola" }]);
  assert.equal(second.rest, "");
});

test("ignores heartbeat comments and malformed data", () => {
  const out = parseSse(': ping\n\ndata: not json\n\ndata: {"type":"done"}\n\n');
  assert.deepEqual(out.events, [{ type: "done" }]);
});

test("an event without a type is dropped", () => {
  assert.deepEqual(parseSse('data: {"x":1}\n\n').events, []);
});
