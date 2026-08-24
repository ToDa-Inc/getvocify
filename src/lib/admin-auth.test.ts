import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  getStoredAdminMasterKey,
  setStoredAdminMasterKey,
  clearStoredAdminMasterKey,
  ADMIN_MASTER_KEY_TTL_MS,
} from "./admin-auth.ts";

function installLocalStorage() {
  const store: Record<string, string> = {};
  const mock: Storage = {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k];
    },
    key: (index: number) => Object.keys(store)[index] ?? null,
    get length() {
      return Object.keys(store).length;
    },
  };
  Object.defineProperty(globalThis, "localStorage", {
    value: mock,
    writable: true,
    configurable: true,
  });
}

describe("admin master key session", () => {
  beforeEach(() => {
    installLocalStorage();
  });

  it("returns null when empty", () => {
    assert.equal(getStoredAdminMasterKey(), null);
  });

  it("round-trips a key", () => {
    setStoredAdminMasterKey("secret");
    assert.equal(getStoredAdminMasterKey(), "secret");
  });

  it("expires after TTL", () => {
    setStoredAdminMasterKey("secret");
    const raw = JSON.parse(localStorage.getItem("vocify_admin_master_key_session")!);
    raw.expiresAt = Date.now() - 1;
    localStorage.setItem("vocify_admin_master_key_session", JSON.stringify(raw));
    assert.equal(getStoredAdminMasterKey(), null);
    assert.equal(localStorage.getItem("vocify_admin_master_key_session"), null);
  });

  it("uses a 7-day TTL", () => {
    assert.equal(ADMIN_MASTER_KEY_TTL_MS, 7 * 24 * 60 * 60 * 1000);
  });

  it("clear removes storage", () => {
    setStoredAdminMasterKey("secret");
    clearStoredAdminMasterKey();
    assert.equal(getStoredAdminMasterKey(), null);
  });
});
