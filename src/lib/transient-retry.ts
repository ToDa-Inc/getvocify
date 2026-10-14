/** A request that got no answer (timeout, network) or hit a failing server may succeed when sent again. */
export function isTransientFailure(error: unknown): boolean {
  if (error instanceof TypeError) return true; // fetch could not reach the server
  const status = (error as { status?: unknown } | null)?.status;
  return typeof status === "number" && (status === 0 || status === 408 || status === 429 || status >= 500);
}

/** After a Vocify call: the live transcript is sent again for about half a minute before the recording takes over. */
export const CALL_UPLOAD_RETRY_DELAYS_MS = [3_000, 8_000, 15_000] as const;

/** Runs `send`, and again after each delay while it fails transiently. Any other failure is thrown at once. */
export async function withTransientRetries<T>(
  send: () => Promise<T>,
  delaysMs: readonly number[],
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await send();
    } catch (error) {
      if (attempt >= delaysMs.length || !isTransientFailure(error)) throw error;
      await sleep(delaysMs[attempt]);
    }
  }
}
