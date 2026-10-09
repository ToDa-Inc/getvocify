import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createLiveTicketCache, type LiveTicket } from "./live-ticket.ts";

const HOUR = 3600;

function setup(issue: (call: number) => Promise<LiveTicket>) {
  let calls = 0;
  let clock = 1_000_000_000_000;
  const cache = createLiveTicketCache(() => issue(++calls), () => clock);
  return { cache, calls: () => calls, advance: (ms: number) => void (clock += ms), expiresIn: (hours: number) => clock / 1000 + hours * HOUR };
}

describe("the live transcription ticket", () => {
  it("is asked for once and reused by the next call", async () => {
    const t = setup(async (n) => ({ ticket: `t${n}`, expires_at: 1_000_000_000 + 12 * HOUR }));
    assert.equal(await t.cache.get("u1"), "t1");
    assert.equal(await t.cache.get("u1"), "t1");
    assert.equal(t.calls(), 1);
  });

  it("is shared by an ask made while another is still waiting", async () => {
    const t = setup(async (n) => ({ ticket: `t${n}`, expires_at: 1_000_000_000 + 12 * HOUR }));
    const [a, b] = await Promise.all([t.cache.get("u1"), t.cache.get("u1")]);
    assert.deepEqual([a, b], ["t1", "t1"]);
    assert.equal(t.calls(), 1);
  });

  it("is never lent to another user", async () => {
    const t = setup(async (n) => ({ ticket: `t${n}`, expires_at: 1_000_000_000 + 12 * HOUR }));
    await t.cache.get("u1");
    assert.equal(await t.cache.get("u2"), "t2");
  });

  it("is asked for again when too little of it is left for a long call", async () => {
    const t = setup(async (n) => ({ ticket: `t${n}`, expires_at: 1_000_000_000 + 12 * HOUR }));
    await t.cache.get("u1");
    t.advance(11.8 * HOUR * 1000);
    assert.equal(await t.cache.get("u1"), "t2");
  });

  it("gives null, and tries again next time, when the API cannot issue one", async () => {
    const t = setup(async (n) => {
      if (n === 1) throw new Error("offline");
      return { ticket: `t${n}`, expires_at: 1_000_000_000 + 12 * HOUR };
    });
    assert.equal(await t.cache.get("u1"), null);
    assert.equal(await t.cache.get("u1"), "t2");
  });

  it("is used once, not kept, when it carries no expiry", async () => {
    const t = setup(async (n) => ({ ticket: `t${n}` }));
    assert.equal(await t.cache.get("u1"), "t1");
    assert.equal(await t.cache.get("u1"), "t2");
  });
});
