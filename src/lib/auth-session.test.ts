import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  createRefreshGate,
  isAccessTokenFresh,
  shouldClearAuthOnRefreshStatus,
} from "./auth-session.ts";

function jwtWithExp(expSeconds: number): string {
  const payload = btoa(JSON.stringify({ exp: expSeconds }));
  return `header.${payload}.sig`;
}

describe("shouldClearAuthOnRefreshStatus", () => {
  it("clears the stored session only on a real 401", () => {
    assert.equal(shouldClearAuthOnRefreshStatus(401), true);
    assert.equal(shouldClearAuthOnRefreshStatus(503), false);
    assert.equal(shouldClearAuthOnRefreshStatus(429), false);
    assert.equal(shouldClearAuthOnRefreshStatus(500), false);
    assert.equal(shouldClearAuthOnRefreshStatus(0), false);
  });
});

describe("isAccessTokenFresh", () => {
  it("is fresh when expiry is more than a minute away", () => {
    const now = 1_700_000_000_000;
    assert.equal(isAccessTokenFresh(jwtWithExp(now / 1000 + 120), now), true);
    assert.equal(isAccessTokenFresh(jwtWithExp(now / 1000 + 10), now), false);
    assert.equal(isAccessTokenFresh("not-a-jwt", now), false);
  });
});

describe("createRefreshGate", () => {
  it("shares one refresh across overlapping callers", async () => {
    let calls = 0;
    const gate = createRefreshGate({
      getAccessToken: () => null,
      isFresh: () => false,
      refresh: async () => {
        calls += 1;
        await new Promise((r) => setTimeout(r, 20));
        return "new-token";
      },
    });
    const [a, b] = await Promise.all([gate(), gate()]);
    assert.equal(a, "new-token");
    assert.equal(b, "new-token");
    assert.equal(calls, 1);
  });

  it("skips GoTrue when the access token is still fresh", async () => {
    let calls = 0;
    const gate = createRefreshGate({
      getAccessToken: () => "still-good",
      isFresh: (token) => token === "still-good",
      refresh: async () => {
        calls += 1;
        return "new-token";
      },
    });
    assert.equal(await gate(), "still-good");
    assert.equal(calls, 0);
  });
});
