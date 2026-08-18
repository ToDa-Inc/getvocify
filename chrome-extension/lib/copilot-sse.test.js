import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { parseSseBuffer } from './copilot-sse.js';

describe('parseSseBuffer', () => {
  it('parses complete SSE data events and keeps a trailing partial', () => {
    const { events, rest } = parseSseBuffer(
      'data: {"type":"token","text":"Hi"}\n\ndata: {"type":"result","suggestion":{"say_this":"Ok"}}\n\ndata: {"type":"don'
    );
    assert.equal(events.length, 2);
    assert.equal(events[0].type, 'token');
    assert.equal(events[0].text, 'Hi');
    assert.equal(events[1].type, 'result');
    assert.equal(events[1].suggestion.say_this, 'Ok');
    assert.equal(rest, 'data: {"type":"don');
  });

  it('ignores malformed JSON chunks', () => {
    const { events, rest } = parseSseBuffer('data: not-json\n\n');
    assert.equal(events.length, 0);
    assert.equal(rest, '');
  });
});
