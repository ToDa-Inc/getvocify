import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { ISLAND_HOST, createIslandRelay } from './island-relay.js';

function harness({ fails = false } = {}) {
  let clock = 0;
  const timers = new Map();
  let nextTimer = 1;
  const ports = [];
  const relay = createIslandRelay({
    connectNative(name) {
      assert.equal(name, ISLAND_HOST);
      if (fails) throw new Error('no host');
      const listeners = [];
      const port = {
        sent: [],
        closed: false,
        postMessage: (m) => port.sent.push(m),
        disconnect: () => { port.closed = true; },
        onDisconnect: { addListener: (fn) => listeners.push(fn) },
        hangUp: () => listeners.forEach((fn) => fn()),
      };
      ports.push(port);
      return port;
    },
    now: () => clock,
    setTimer: (fn, ms) => { const id = nextTimer++; timers.set(id, { fn, at: clock + ms }); return id; },
    clearTimer: (id) => timers.delete(id),
    idleMs: 10_000,
    retryMs: 30_000,
  });
  const advance = (ms) => {
    clock += ms;
    for (const [id, t] of [...timers]) if (t.at <= clock) { timers.delete(id); t.fn(); }
  };
  return { relay, ports, advance };
}

describe('island relay', () => {
  it('opens one port for a call and sends each reading', () => {
    const { relay, ports } = harness();
    assert.equal(relay.send(['Marta']), true);
    assert.equal(relay.send([]), true);
    assert.equal(ports.length, 1);
    assert.deepEqual(ports[0].sent, [
      { type: 'meet-speakers', speaking: ['Marta'] },
      { type: 'meet-speakers', speaking: [] },
    ]);
  });

  it('closes the port once readings stop', () => {
    const { relay, ports, advance } = harness();
    relay.send(['Marta']);
    advance(9_000);
    relay.send(['Marta']);
    advance(9_000);
    assert.equal(ports[0].closed, false);
    advance(2_000);
    assert.equal(ports[0].closed, true);
    relay.send(['Juan']);
    assert.equal(ports.length, 2);
  });

  it('without the Mac app, waits before trying again', () => {
    const { relay, ports, advance } = harness();
    relay.send(['Marta']);
    ports[0].hangUp();
    assert.equal(relay.send(['Marta']), false);
    advance(31_000);
    assert.equal(relay.send(['Marta']), true);
    assert.equal(ports.length, 2);
  });

  it('a connect that throws is retried later, not every reading', () => {
    const { relay } = harness({ fails: true });
    assert.equal(relay.send(['Marta']), false);
    assert.equal(relay.send(['Marta']), false);
  });
});
