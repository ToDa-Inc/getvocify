/**
 * The live transcription service's pass, kept for the day it is good for.
 *
 * The API issues it (POST /transcription/ticket) as a signed token naming the user, valid for hours and reusable, so
 * a call never needs a fresh one: asking at the moment a call is answered put a network round trip between "answered"
 * and the first word on screen. It is asked for while the call rings instead, and kept for the next one.
 */
export type LiveTicket = { ticket: string; expires_at?: number };

/** A ticket this close to its end is not reused: a long call could outlive it when its socket reconnects. */
const MARGIN_MS = 30 * 60 * 1000;

export function createLiveTicketCache(fetchTicket: () => Promise<LiveTicket>, now: () => number = Date.now) {
  let held: { userId: string; ticket: string; until: number } | null = null;
  let asking: { userId: string; request: Promise<string | null> } | null = null;

  return {
    /** The user's ticket, from the cache when it is good for a while yet; null when the API could not give one. */
    get(userId: string): Promise<string | null> {
      if (held && held.userId === userId && held.until > now()) return Promise.resolve(held.ticket);
      // Two askers at once (the ringing call and its start) share one request.
      if (asking && asking.userId === userId) return asking.request;
      const request = fetchTicket()
        .then((issued) => {
          // Without an expiry it cannot be judged later, so it is used once and not kept.
          if (typeof issued.expires_at === "number") held = { userId, ticket: issued.ticket, until: issued.expires_at * 1000 - MARGIN_MS };
          return issued.ticket;
        })
        .catch(() => null)
        .finally(() => {
          if (asking?.request === request) asking = null;
        });
      asking = { userId, request };
      return request;
    },
  };
}
