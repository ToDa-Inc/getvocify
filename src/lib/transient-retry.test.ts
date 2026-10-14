import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { isTransientFailure, withTransientRetries } from "./transient-retry.ts";

const status = (code: number) => Object.assign(new Error(`HTTP ${code}`), { status: code });

describe("transient failures", () => {
  it("are no answer, a network error or a failing server", () => {
    assert.equal(isTransientFailure(status(0)), true); // timed out
    assert.equal(isTransientFailure(new TypeError("Failed to fetch")), true);
    assert.equal(isTransientFailure(status(502)), true);
    assert.equal(isTransientFailure(status(503)), true);
    assert.equal(isTransientFailure(status(429)), true);
  });

  it("are never a request the server refused", () => {
    assert.equal(isTransientFailure(status(400)), false);
    assert.equal(isTransientFailure(status(404)), false);
    assert.equal(isTransientFailure(status(403)), false);
    assert.equal(isTransientFailure(new Error("bug")), false);
  });
});

describe("withTransientRetries", () => {
  const noWait = async () => {};

  it("sends again after a timeout and returns the answer that came", async () => {
    let sent = 0;
    const result = await withTransientRetries(
      async () => {
        sent += 1;
        if (sent < 3) throw status(0);
        return "memo-1";
      },
      [10, 10, 10],
      noWait,
    );
    assert.equal(result, "memo-1");
    assert.equal(sent, 3);
  });

  it("waits the given delays between attempts", async () => {
    const waited: number[] = [];
    await assert.rejects(
      withTransientRetries(async () => Promise.reject(status(502)), [3, 8, 15], async (ms) => {
        waited.push(ms);
      }),
    );
    assert.deepEqual(waited, [3, 8, 15]);
  });

  it("gives up with the last failure once the delays run out", async () => {
    let sent = 0;
    await assert.rejects(
      withTransientRetries(
        async () => {
          sent += 1;
          throw status(503);
        },
        [1, 1],
        noWait,
      ),
      /HTTP 503/,
    );
    assert.equal(sent, 3);
  });

  it("does not resend what the server refused", async () => {
    let sent = 0;
    await assert.rejects(
      withTransientRetries(
        async () => {
          sent += 1;
          throw status(404);
        },
        [1, 1, 1],
        noWait,
      ),
    );
    assert.equal(sent, 1);
  });
});
