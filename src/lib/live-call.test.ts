import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  followLiveCalls,
  isLiveCallOpen,
  liveCallReconnectDelay,
  parseLiveCallSse,
  type LiveCall,
  type LiveCallStreamEvent,
} from "./live-call.ts";

const call = (over: Partial<LiveCall> = {}): LiveCall => ({
  external_call_id: "ac-1",
  provider: "hubspot",
  source: "hubspot_calling_sdk",
  status: "dialing",
  direction: "outbound",
  remote_number: "+34600111222",
  started_at: 1,
  updated_at: 1,
  contact_id: "901",
  contact_name: null,
  contact_source: "page",
  page_object_type: "contact",
  page_record_id: "901",
  answered_at: null,
  ended_at: null,
  end_status: null,
  engagement_id: null,
  ...over,
});

const sse = (event: unknown) => `data: ${JSON.stringify(event)}\n\n`;

describe("parseLiveCallSse", () => {
  it("emits complete events and keeps the partial tail", () => {
    const got: LiveCallStreamEvent[] = [];
    const text = sse({ type: "snapshot", call: null }) + ": keepalive\n\n" + sse({ type: "call", call: call() });
    const rest = parseLiveCallSse("", text.slice(0, 20), (e) => got.push(e));
    assert.equal(got.length, 0);
    const left = parseLiveCallSse(rest, text.slice(20), (e) => got.push(e));
    assert.equal(left, "");
    assert.deepEqual(got.map((e) => e.type), ["snapshot", "call"]);
    assert.equal(got[1].call?.contact_id, "901");
  });

  it("skips malformed and unknown events", () => {
    const got: LiveCallStreamEvent[] = [];
    parseLiveCallSse("", "data: {oops\n\n" + sse({ type: "other" }) + sse({ type: "call", call: null }), (e) => got.push(e));
    assert.equal(got.length, 0);
  });

  it("handles CRLF line endings", () => {
    const got: LiveCallStreamEvent[] = [];
    parseLiveCallSse("", sse({ type: "snapshot", call: null }).replace(/\n/g, "\r\n"), (e) => got.push(e));
    assert.equal(got.length, 1);
  });
});

describe("isLiveCallOpen", () => {
  it("is open while dialing or connected", () => {
    assert.equal(isLiveCallOpen(call({ status: "dialing" })), true);
    assert.equal(isLiveCallOpen(call({ status: "connected" })), true);
    assert.equal(isLiveCallOpen(call({ status: "ended" })), false);
    assert.equal(isLiveCallOpen(null), false);
  });
});

describe("liveCallReconnectDelay", () => {
  it("backs off and caps at 30s", () => {
    assert.deepEqual([0, 1, 2, 10].map(liveCallReconnectDelay), [1000, 2000, 4000, 30000]);
  });
});

function streamResponse(chunks: string[]): Response {
  const enc = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const c of chunks) controller.enqueue(enc.encode(c));
        controller.close();
      },
    }),
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
}

describe("followLiveCalls", () => {
  it("delivers calls, reconnects after the stream ends, and stops on abort", async () => {
    const ctrl = new AbortController();
    const seen: (LiveCall | null)[] = [];
    const connected: boolean[] = [];
    const sleeps: number[] = [];
    const auths: string[] = [];
    let n = 0;
    const fetchImpl = (async (_url: string, init: RequestInit) => {
      auths.push((init.headers as Record<string, string>).Authorization);
      n += 1;
      if (n === 1) return streamResponse([sse({ type: "snapshot", call: null }), sse({ type: "call", call: call() })]);
      if (n === 2) return new Response("nope", { status: 401 });
      ctrl.abort();
      return streamResponse([sse({ type: "snapshot", call: call({ status: "connected" }) })]);
    }) as typeof fetch;

    await followLiveCalls({
      url: "http://api/live-calls/stream",
      getToken: () => "tok",
      onCall: (c) => seen.push(c),
      onConnectedChange: (c) => connected.push(c),
      signal: ctrl.signal,
      fetchImpl,
      sleep: async (ms) => { sleeps.push(ms); },
    });

    assert.deepEqual(seen.map((c) => c?.status ?? null), [null, "dialing", "connected"]);
    assert.deepEqual(auths, ["Bearer tok", "Bearer tok", "Bearer tok"]);
    assert.deepEqual(sleeps, [1000, 2000]);
    assert.equal(connected[0], true);
    assert.equal(connected.at(-1), false);
  });

  it("waits without calling the API while signed out", async () => {
    const ctrl = new AbortController();
    let fetched = 0;
    let slept = 0;
    await followLiveCalls({
      url: "x",
      getToken: () => null,
      onCall: () => {},
      signal: ctrl.signal,
      fetchImpl: (async () => { fetched += 1; return new Response(); }) as typeof fetch,
      sleep: async () => { slept += 1; if (slept === 3) ctrl.abort(); },
    });
    assert.equal(fetched, 0);
    assert.equal(slept, 3);
  });
});
