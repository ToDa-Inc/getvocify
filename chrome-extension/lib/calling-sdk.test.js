import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  CALLING_SDK_MESSAGE_TYPES,
  buildLiveCallEventBody,
  createLiveCallTracker,
  parseCallingSdkMessage,
  pickCallRecord,
} from './calling-sdk.js';
import { parseCrmPageUrl } from './crm-page.js';
import { readFileSync } from 'node:fs';

// Shapes as posted by @hubspot/calling-extensions-sdk IFrameManager.sendMessage:
// { type, data, messageId }.
const started = {
  type: 'OUTGOING_CALL_STARTED',
  data: { externalCallId: 'ac-1', toNumber: '+34600111222', fromNumber: '+34910000000', callStartTime: 1, createEngagement: true },
  messageId: '1700000000000_1',
};

describe('parseCallingSdkMessage', () => {
  it('maps an outgoing call start', () => {
    assert.deepEqual(parseCallingSdkMessage(started), {
      event: 'started',
      direction: 'outbound',
      externalCallId: 'ac-1',
      toNumber: '+34600111222',
      fromNumber: '+34910000000',
      endStatus: null,
      engagementId: null,
    });
  });

  it('maps incoming, answered, ended and completed', () => {
    assert.equal(parseCallingSdkMessage({ type: 'INCOMING_CALL', data: { externalCallId: 'x', fromNumber: '+1' } }).direction, 'inbound');
    assert.equal(parseCallingSdkMessage({ type: 'CALL_ANSWERED', data: { externalCallId: 'x' } }).event, 'answered');
    const ended = parseCallingSdkMessage({ type: 'CALL_ENDED', data: { externalCallId: 'x', engagementId: 42, callEndStatus: 'COMPLETED' } });
    assert.equal(ended.event, 'ended');
    assert.equal(ended.endStatus, 'COMPLETED');
    assert.equal(ended.engagementId, '42');
    assert.equal(parseCallingSdkMessage({ type: 'CALL_COMPLETED', data: { externalCallId: 'x', engagementId: '9' } }).event, 'completed');
  });

  it('accepts the legacy phoneNumber field', () => {
    assert.equal(parseCallingSdkMessage({ type: 'OUTGOING_CALL_STARTED', data: { phoneNumber: '+44700' } }).toNumber, '+44700');
  });

  it('ignores non-call SDK traffic and junk', () => {
    for (const msg of [null, 'x', {}, { type: 'SYNC' }, { type: 'DIAL_NUMBER', data: {} }, { type: 'RESIZE_WIDGET' }]) {
      assert.equal(parseCallingSdkMessage(msg), null);
    }
  });

  it('matches the list the content script filters on', () => {
    const src = readFileSync(new URL('../content/hubspot-calling.js', import.meta.url), 'utf8');
    for (const type of CALLING_SDK_MESSAGE_TYPES) assert.ok(src.includes(`'${type}'`), type);
  });
});

describe('createLiveCallTracker', () => {
  it('passes events through once and drops quick repeats', () => {
    let t = 1000;
    const tracker = createLiveCallTracker({ now: () => t });
    assert.ok(tracker.accept(parseCallingSdkMessage(started), 1));
    assert.equal(tracker.accept(parseCallingSdkMessage(started), 1), null);
    t += 6000;
    assert.ok(tracker.accept(parseCallingSdkMessage(started), 1));
  });

  it('gives id-less events the id of the call started on that tab', () => {
    let t = 1000;
    const tracker = createLiveCallTracker({ now: () => t });
    const start = tracker.accept(parseCallingSdkMessage({ type: 'OUTGOING_CALL_STARTED', data: { toNumber: '+1' } }), 7);
    assert.match(start.externalCallId, /^synthetic-7-/);
    t += 10;
    const answered = tracker.accept(parseCallingSdkMessage({ type: 'CALL_ANSWERED', data: {} }), 7);
    assert.equal(answered.externalCallId, start.externalCallId);
    assert.equal(tracker.accept(parseCallingSdkMessage({ type: 'CALL_ANSWERED', data: {} }), 8), null);
  });
});

describe('buildLiveCallEventBody', () => {
  const tracked = { ...parseCallingSdkMessage(started) };

  it('sends the HubSpot contact record the rep is on', () => {
    assert.deepEqual(
      buildLiveCallEventBody(tracked, { provider: 'hubspot', objectType: 'contact', recordId: '901' }),
      {
        provider: 'hubspot',
        source: 'hubspot_calling_sdk',
        event: 'started',
        external_call_id: 'ac-1',
        direction: 'outbound',
        to_number: '+34600111222',
        from_number: '+34910000000',
        page_object_type: 'contact',
        page_record_id: '901',
      },
    );
  });

  it('leaves out records that are not HubSpot contacts, companies or deals', () => {
    for (const page of [
      null,
      { provider: 'pipedrive', objectType: 'contact', recordId: '5' },
      { provider: 'hubspot', objectType: 'ticket', recordId: '5' },
      { provider: 'hubspot', objectType: 'contact', recordId: 'abc' },
    ]) {
      const body = buildLiveCallEventBody(tracked, page);
      assert.equal(body.page_object_type, undefined);
      assert.equal(body.page_record_id, undefined);
    }
  });
});

describe('pickCallRecord', () => {
  const REC = (id) => `https://app-eu1.hubspot.com/contacts/1234/record/0-1/${id}`;
  const pick = (senderUrl, hubspotTabs) => pickCallRecord({ senderUrl, hubspotTabs, parseUrl: parseCrmPageUrl });

  it('uses the dialer tab when it is a record page', () => {
    const got = pick(REC(1), [{ url: REC(2), lastAccessed: 999 }]);
    assert.equal(got.recordId, '1');
  });

  it('uses the most recently used record tab for a calling window', () => {
    const got = pick('https://app-eu1.hubspot.com/calling-window/1234', [
      { url: REC(2), lastAccessed: 100 },
      { url: REC(3), lastAccessed: 300 },
      { url: 'https://app-eu1.hubspot.com/calling-window/1234', lastAccessed: 400 },
      { url: 'https://app-eu1.hubspot.com/reports-dashboard/1234', lastAccessed: 500 },
    ]);
    assert.equal(got.recordId, '3');
  });

  it('returns null when no HubSpot record is open', () => {
    assert.equal(pick('https://app.hubspot.com/calling-window/1', []), null);
    assert.equal(pick(null, [{ url: 'https://app.hubspot.com/reports-dashboard/1' }]), null);
  });
});
