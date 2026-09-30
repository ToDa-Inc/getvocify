/**
 * Runs in every HubSpot frame. Embedded dialers (Aircall, Ringover, …) post
 * their call lifecycle to the page through HubSpot's Calling Extensions SDK;
 * this forwards those messages to the service worker, which does the rest
 * (lib/calling-sdk.js). Classic script: content scripts cannot be modules.
 * Keep the type list in sync with CALLING_SDK_MESSAGE_TYPES.
 */
(() => {
  const CALL_TYPES = new Set([
    'OUTGOING_CALL_STARTED',
    'INCOMING_CALL',
    'CALL_ANSWERED',
    'CALL_ENDED',
    'CALL_COMPLETED',
  ]);

  window.addEventListener('message', (event) => {
    const msg = event.data;
    if (!msg || typeof msg !== 'object' || !CALL_TYPES.has(msg.type)) return;
    let data = null;
    try {
      data = msg.data == null ? null : JSON.parse(JSON.stringify(msg.data));
    } catch {
      return;
    }
    try {
      chrome.runtime.sendMessage({
        type: 'CALLING_SDK_MESSAGE',
        message: { type: msg.type, data },
      }).catch(() => {});
    } catch {
      // Extension reloaded or updated: this page's context is gone until reload.
    }
  });
})();
