/**
 * Dashboard session policy. Access JWTs stay short-lived; refresh tokens
 * keep the user signed in. Only a real 401 from /auth/refresh means logout.
 */

export function shouldClearAuthOnRefreshStatus(status: number): boolean {
  return status === 401;
}

/** /auth/me 404 = JWT ok, no Vocify profile. 401 = session dead. */
export function shouldClearAuthOnMeStatus(status: number): boolean {
  return status === 401 || status === 404;
}

export type SessionGateView = "loading" | "login" | "restore-failed" | "ok";

export function sessionGateView(args: {
  isLoading: boolean;
  hasStoredSession: boolean;
  isAuthenticated: boolean;
}): SessionGateView {
  if (args.isLoading) return "loading";
  if (!args.hasStoredSession) return "login";
  if (!args.isAuthenticated) return "restore-failed";
  return "ok";
}

export function getTokenExpiryMs(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload?.exp ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

export function isAccessTokenFresh(
  token: string,
  nowMs = Date.now(),
  minTtlMs = 60_000,
): boolean {
  const exp = getTokenExpiryMs(token);
  if (!exp) return false;
  return exp - nowMs > minTtlMs;
}

type RefreshGateOptions = {
  getAccessToken: () => string | null;
  isFresh: (token: string) => boolean;
  refresh: () => Promise<string | null>;
};

/** One in-flight refresh per JS context. Cross-tab races need Web Locks too. */
export function createRefreshGate(options: RefreshGateOptions): () => Promise<string | null> {
  let inflight: Promise<string | null> | null = null;
  return () => {
    if (!inflight) {
      inflight = Promise.resolve()
        .then(() => {
          const current = options.getAccessToken();
          if (current && options.isFresh(current)) return current;
          return options.refresh();
        })
        .finally(() => {
          inflight = null;
        });
    }
    return inflight;
  };
}
