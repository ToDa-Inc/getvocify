// One reading of each producer in flight (spec 2026-10-16, "Concurrency"): a checkpoint that arrives while a reading runs is
// kept as the next one, the latest words win, and a rep's ask (Responder / Preguntar / Resumen) is never lost to an automatic
// checkpoint. The renderer makes one reader per producer; `run` does the request and merges its result into the state.

/**
 * @template T
 * @param {(request: T, options: {asked: boolean}) => Promise<unknown>} run
 * @returns {{ request: (request: T, options?: {asked?: boolean}) => void, busy: () => boolean }}
 */
export function createReader(run) {
  let running = false;
  /** @type {{request: T, asked: boolean} | null} */
  let next = null;

  async function go(request, asked) {
    running = true;
    try {
      await run(request, { asked });
    } catch {
      /* the caller's run handles its own errors; a failed reading must not stop the next one */
    } finally {
      running = false;
      if (next) {
        const queued = next;
        next = null;
        void go(queued.request, queued.asked);
      }
    }
  }

  return {
    request(request, { asked = false } = {}) {
      if (!running) return void go(request, asked);
      // Latest words win; but what the rep asked for stays asked even when a newer automatic checkpoint replaces its words.
      next = { request, asked: asked || Boolean(next?.asked) };
    },
    busy: () => running,
  };
}
