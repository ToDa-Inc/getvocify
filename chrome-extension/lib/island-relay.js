/**
 * Passes Meet speaker readings to the Vocify Mac app through Chrome native messaging.
 * Chrome starts the app's helper on connect and stops it on disconnect, so the port opens
 * with the first reading of a call and closes once readings stop.
 */
export const ISLAND_HOST = 'com.vocify.speakers';

export function createIslandRelay({
  connectNative,
  now = () => Date.now(),
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
  idleMs = 10_000,
  retryMs = 30_000,
}) {
  let port = null;
  let idle = null;
  let retryAt = 0;

  function close() {
    if (idle !== null) clearTimer(idle);
    idle = null;
    const open = port;
    port = null;
    open?.disconnect();
  }

  function open() {
    if (port || now() < retryAt) return port;
    try {
      port = connectNative(ISLAND_HOST);
    } catch {
      retryAt = now() + retryMs;
      return null;
    }
    // No Mac app installed (host not found) or it went away: try again later, quietly.
    const opened = port;
    opened.onDisconnect.addListener(() => {
      void globalThis.chrome?.runtime?.lastError;
      if (port === opened) port = null;
      retryAt = now() + retryMs;
    });
    return port;
  }

  return {
    send(speaking) {
      const target = open();
      if (!target) return false;
      try {
        target.postMessage({ type: 'meet-speakers', speaking });
      } catch {
        close();
        return false;
      }
      if (idle !== null) clearTimer(idle);
      idle = setTimer(close, idleMs);
      return true;
    },
    close,
  };
}
