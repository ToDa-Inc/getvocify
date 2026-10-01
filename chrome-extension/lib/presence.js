/**
 * Where the rep is in the CRM, for the backend's live call contact.
 *
 * When the rep's desktop app starts a call, the contact is the record they
 * had open. Pure module: the service worker owns the timers and the request.
 */

const HUBSPOT_APP = /^https:\/\/app(?:-[a-z0-9]+)?\.hubspot\.com\//i;
const PIPEDRIVE_APP = /^https:\/\/(?!(?:api|oauth|www|developers|app)\.)[a-z0-9-]+\.pipedrive\.com\//i;
// HubSpot's calling window and calling frames are not where the rep is: the
// record they clicked Call on stays the answer.
const HUBSPOT_CALLING = /\.hubspot\.com\/(?:calling-integration-popup-ui|calling-cross-tab-embed|calling)\//i;
const OBJECT_TYPES = new Set(['contact', 'company', 'deal']);

export const PRESENCE_HEARTBEAT_MS = 5 * 60 * 1000;

/**
 * PUT /live-calls/presence body for a tab URL, or null when the URL says
 * nothing about where the rep is (not a CRM page, or HubSpot's calling window).
 * `parsed` is parseCrmPageUrl(url).
 */
export function presenceFromUrl(url, parsed) {
  if (!url || typeof url !== 'string') return null;
  if (HUBSPOT_CALLING.test(url)) return null;
  const provider = HUBSPOT_APP.test(url) ? 'hubspot' : PIPEDRIVE_APP.test(url) ? 'pipedrive' : null;
  if (!provider) return null;

  const recordId = parsed?.recordId != null ? String(parsed.recordId) : '';
  if (parsed?.provider === provider && OBJECT_TYPES.has(parsed.objectType) && /^\d{1,32}$/.test(recordId)) {
    const account = provider === 'hubspot' ? parsed.hubId : parsed.companyDomain;
    return {
      provider,
      object_type: parsed.objectType,
      record_id: recordId,
      ...(account ? { account_id: String(account) } : {}),
    };
  }
  // A CRM page that is not a record (list, sequence, inbox): a call started
  // here has no known contact, so the previous record must not be used.
  return { provider };
}

/**
 * Sends a presence when it changes, and the same one again once per
 * heartbeat so a rep who stays on one record never looks stale.
 */
export function createPresenceReporter({ send, now = () => Date.now(), heartbeatMs = PRESENCE_HEARTBEAT_MS }) {
  let lastKey = null;
  let lastAt = 0;
  return {
    report(presence) {
      if (!presence) return false;
      const key = JSON.stringify(presence);
      const t = now();
      if (key === lastKey && t - lastAt < heartbeatMs) return false;
      lastKey = key;
      lastAt = t;
      Promise.resolve(send(presence)).catch(() => {
        // Not delivered: let the next look retry instead of waiting a heartbeat.
        if (lastKey === key) lastKey = null;
      });
      return true;
    },
  };
}
