import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createReader } from "./reader.js";

const gate = () => {
  let open;
  const promise = new Promise((resolve) => (open = resolve));
  return { promise, open };
};

describe("createReader", () => {
  it("runs one reading at a time and coalesces what arrives meanwhile into the latest", async () => {
    const seen = [];
    const first = gate();
    const reader = createReader(async (request) => {
      seen.push(request);
      if (request === "a") await first.promise;
    });
    reader.request("a");
    reader.request("b");
    reader.request("c");
    assert.ok(reader.busy());
    assert.deepEqual(seen, ["a"]);
    first.open();
    await new Promise((resolve) => setTimeout(resolve, 5));
    assert.deepEqual(seen, ["a", "c"]); // b was replaced by the newer words
    assert.ok(!reader.busy());
  });

  it("keeps what the rep asked when a newer automatic checkpoint replaces its words", async () => {
    const seen = [];
    const first = gate();
    const reader = createReader(async (request, { asked }) => {
      seen.push({ n: request.n, asked });
      if (request.n === 1) await first.promise;
    });
    reader.request({ n: 1 });
    reader.request({ n: 2 }, { asked: true });
    reader.request({ n: 3 });
    first.open();
    await new Promise((resolve) => setTimeout(resolve, 5));
    assert.deepEqual(seen, [{ n: 1, asked: false }, { n: 3, asked: true }]);
  });

  it("a failing reading does not stop the next", async () => {
    const seen = [];
    const first = gate();
    const reader = createReader(async (request) => {
      seen.push(request);
      if (request === "a") {
        await first.promise;
        throw new Error("offline");
      }
    });
    reader.request("a");
    reader.request("b");
    first.open();
    await new Promise((resolve) => setTimeout(resolve, 5));
    assert.deepEqual(seen, ["a", "b"]);
  });
});
