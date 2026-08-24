const IMPERSONATION_KEY = "vocify_admin_impersonation";
const SAVED_SESSION_KEY = "vocify_admin_saved_session";
const TOKEN_KEY = "vocify_token";
const REFRESH_KEY = "vocify_refresh";

export type ImpersonationMeta = {
  accountId: string;
  email: string;
  fullName: string | null;
  startedAt: string;
};

type SavedSession = {
  accessToken: string;
  refreshToken: string;
} | null;

export function getImpersonation(): ImpersonationMeta | null {
  const raw = localStorage.getItem(IMPERSONATION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ImpersonationMeta;
  } catch {
    return null;
  }
}

export function setImpersonation(meta: ImpersonationMeta): void {
  localStorage.setItem(IMPERSONATION_KEY, JSON.stringify(meta));
}

export function clearImpersonation(): void {
  localStorage.removeItem(IMPERSONATION_KEY);
}

export function saveCustomerSessionForReturn(): void {
  const accessToken = localStorage.getItem(TOKEN_KEY);
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  const payload: SavedSession =
    accessToken && refreshToken ? { accessToken, refreshToken } : null;
  localStorage.setItem(SAVED_SESSION_KEY, JSON.stringify(payload));
}

export function restoreCustomerSessionAfterImpersonation(): void {
  const raw = localStorage.getItem(SAVED_SESSION_KEY);
  let saved: SavedSession = null;
  if (raw) {
    try {
      saved = JSON.parse(raw) as SavedSession;
    } catch {
      saved = null;
    }
  }
  if (saved?.accessToken && saved.refreshToken) {
    localStorage.setItem(TOKEN_KEY, saved.accessToken);
    localStorage.setItem(REFRESH_KEY, saved.refreshToken);
  } else {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  }
  localStorage.removeItem(SAVED_SESSION_KEY);
  clearImpersonation();
}

export async function loginAsAccount(args: {
  accountId: string;
  email: string;
  fullName: string | null;
  impersonate: (id: string) => Promise<{ accessToken: string; refreshToken: string }>;
}): Promise<void> {
  const session = await args.impersonate(args.accountId);
  saveCustomerSessionForReturn();
  setImpersonation({
    accountId: args.accountId,
    email: args.email,
    fullName: args.fullName,
    startedAt: new Date().toISOString(),
  });
  localStorage.setItem(TOKEN_KEY, session.accessToken);
  localStorage.setItem(REFRESH_KEY, session.refreshToken);
  window.location.assign("/dashboard");
}

export function returnToAdmin(): void {
  restoreCustomerSessionAfterImpersonation();
  window.location.assign("/admin");
}
