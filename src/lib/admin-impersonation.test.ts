import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  getImpersonation,
  setImpersonation,
  clearImpersonation,
  saveCustomerSessionForReturn,
  restoreCustomerSessionAfterImpersonation,
} from "./admin-impersonation.ts";

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

describe("admin impersonation storage", () => {
  beforeEach(() => {
    installLocalStorage();
  });

  it("stores viewing-as meta", () => {
    setImpersonation({ accountId: "u1", email: "a@b.c", fullName: "Ada", startedAt: "t" });
    assert.equal(getImpersonation()?.email, "a@b.c");
    clearImpersonation();
    assert.equal(getImpersonation(), null);
  });

  it("saves and restores customer tokens", () => {
    localStorage.setItem("vocify_token", "old-access");
    localStorage.setItem("vocify_refresh", "old-refresh");
    saveCustomerSessionForReturn();
    localStorage.setItem("vocify_token", "impersonated");
    localStorage.setItem("vocify_refresh", "imp-refresh");
    restoreCustomerSessionAfterImpersonation();
    assert.equal(localStorage.getItem("vocify_token"), "old-access");
    assert.equal(localStorage.getItem("vocify_refresh"), "old-refresh");
  });

  it("clears tokens when there was no prior session", () => {
    saveCustomerSessionForReturn();
    localStorage.setItem("vocify_token", "impersonated");
    restoreCustomerSessionAfterImpersonation();
    assert.equal(localStorage.getItem("vocify_token"), null);
  });
});
