const STORAGE_KEY = "vocify_admin_master_key_session";

/** Admin master key persists in localStorage for 7 days on this browser. */
export const ADMIN_MASTER_KEY_TTL_MS = 7 * 24 * 60 * 60 * 1000;

type StoredAdminSession = {
  key: string;
  expiresAt: number;
};

function parseStored(raw: string | null): StoredAdminSession | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredAdminSession>;
    if (typeof parsed.key === "string" && typeof parsed.expiresAt === "number") {
      return { key: parsed.key, expiresAt: parsed.expiresAt };
    }
  } catch {
    /* ignore corrupt storage */
  }
  return null;
}

export function getStoredAdminMasterKey(): string | null {
  const stored = parseStored(localStorage.getItem(STORAGE_KEY));
  if (stored) {
    if (Date.now() > stored.expiresAt) {
      clearStoredAdminMasterKey();
      return null;
    }
    return stored.key;
  }
  return null;
}

export function setStoredAdminMasterKey(key: string): void {
  const payload: StoredAdminSession = {
    key,
    expiresAt: Date.now() + ADMIN_MASTER_KEY_TTL_MS,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

export function clearStoredAdminMasterKey(): void {
  localStorage.removeItem(STORAGE_KEY);
}
