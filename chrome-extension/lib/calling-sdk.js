/**
 * HubSpot Calling Extensions SDK messages → Vocify live call events.
 *
 * Any dialer embedded in HubSpot (Aircall, Ringover, …) runs in an iframe and
 * reports its calls to the HubSpot page with window.postMessage. Message
 * shapes follow @hubspot/calling-extensions-sdk (src/Constants.ts,
 * src/types.ts): { type, data, messageId }. The content script forwards the
 * call messages here; this module owns every decision so it stays testable.
 */

export const CALLING_SDK_MESSAGE_TYPES = Object.freeze([
  'OUTGOING_CALL_STARTED',
  'INCOMING_CALL',
  'CALL_ANSWERED',
  'CALL_ENDED',
  'CALL_COMPLETED',
]);

const EVENT_FOR_TYPE = {
  OUTGOING_CALL_STARTED: 'started',
  INCOMING_CALL: 'started',
  CALL_ANSWERED: 'answered',
  CALL_ENDED: 'ended',
  CALL_COMPLETED: 'completed',
};

const DUPLICATE_WINDOW_MS = 5000;
const MAX_TEXT = 200;

function text(value, max = MAX_TEXT) {
  if (value == null) return null;
  const s = String(value).trim();
  return s ? s.slice(0, max) : null;
}

/**
 * Normalize one SDK message. Returns null for anything that is not a call
 * lifecycle message.
 */
export function parseCallingSdkMessage(message) {
  if (!message || typeof message !== 'object') return null;
  const event = EVENT_FOR_TYPE[message.type];
  if (!event) return null;
  const data = message.data && typeof message.data === 'object' ? message.data : {};
  return {
    event,
    direction: message.type === 'INCOMING_CALL' ? 'inbound' : 'outbound',
    externalCallId: text(data.externalCallId),
    toNumber: text(data.toNumber ?? data.phoneNumber, 40),
    fromNumber: text(data.fromNumber, 40),
    endStatus: text(data.callEndStatus, 40),
    engagementId: text(data.engagementId, 64),
  };
}

/**
 * Gives every event a call id and drops repeats.
 *
 * Older SDK builds send no externalCallId, so a start without one opens a
 * synthetic id that later id-less events on the same tab reuse.
 */
export function createLiveCallTracker({ now = () => Date.now() } = {}) {
  const currentByTab = new Map();
  const seen = new Map();

  return {
    accept(parsed, tabKey = 'default') {
      if (!parsed) return null;
      const t = now();
      let callId = parsed.externalCallId;
      if (!callId) {
        if (parsed.event === 'started') {
          callId = `synthetic-${tabKey}-${t}`;
        } else {
          callId = currentByTab.get(tabKey) || null;
        }
      }
      if (!callId) return null;
      if (parsed.event === 'started') currentByTab.set(tabKey, callId);

      const key = `${callId}:${parsed.event}`;
      const last = seen.get(key);
      if (last != null && t - last < DUPLICATE_WINDOW_MS) return null;
      seen.set(key, t);
      for (const [k, at] of seen) {
        if (t - at > DUPLICATE_WINDOW_MS) seen.delete(k);
      }
      return { ...parsed, externalCallId: callId };
    },
  };
}

/**
 * The CRM record a call belongs to.
 *
 * The dialer's own tab wins when it is a record page (dialer docked on the
 * record). HubSpot can also run the dialer in a separate calling window; then
 * the call belongs to the HubSpot record tab the rep used last, which is where
 * they clicked Call.
 */
export function pickCallRecord({ senderUrl = null, hubspotTabs = [], parseUrl }) {
  const own = senderUrl ? parseUrl(senderUrl) : null;
  if (own?.recordId) return own;
  let best = null;
  let bestAt = -Infinity;
  for (const tab of hubspotTabs) {
    if (!tab?.url || tab.url === senderUrl) continue;
    const record = parseUrl(tab.url);
    if (!record?.recordId) continue;
    const at = Number(tab.lastAccessed) || 0;
    if (at > bestAt) {
      best = record;
      bestAt = at;
    }
  }
  return best;
}

const PAGE_OBJECT_TYPES = new Set(['contact', 'company', 'deal']);

/**
 * Request body for POST /live-calls/events.
 *
 * `page` is the parsed CRM record the rep is on (crm-page.js shape). Only a
 * HubSpot record with a numeric id is sent; anything else is left for the
 * backend's phone lookup.
 */
export function buildLiveCallEventBody(tracked, page) {
  const body = {
    provider: 'hubspot',
    source: 'hubspot_calling_sdk',
    event: tracked.event,
    external_call_id: tracked.externalCallId,
    direction: tracked.direction,
  };
  if (tracked.toNumber) body.to_number = tracked.toNumber;
  if (tracked.fromNumber) body.from_number = tracked.fromNumber;
  if (tracked.endStatus) body.end_status = tracked.endStatus;
  if (tracked.engagementId) body.engagement_id = tracked.engagementId;

  const recordId = page?.recordId != null ? String(page.recordId) : '';
  if (
    page &&
    (page.provider === 'hubspot' || page.provider == null) &&
    PAGE_OBJECT_TYPES.has(page.objectType) &&
    /^\d{1,32}$/.test(recordId)
  ) {
    body.page_object_type = page.objectType;
    body.page_record_id = recordId;
  }
  return body;
}
