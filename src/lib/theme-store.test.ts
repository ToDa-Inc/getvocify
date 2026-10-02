import { describe, it } from "node:test";
import assert from "node:assert/strict";

type Store = typeof import("./theme-store.ts");

let instance = 0;
/** A fresh copy of the store (it caches the stored choice) over the given storage. */
async function storeWith(localStorage: Partial<Storage>): Promise<Store> {
  (globalThis as { window?: unknown }).window = { localStorage };
  instance += 1;
  return import(`./theme-store.ts?instance=${instance}`) as Promise<Store>;
}

const denied = () => {
  throw new Error("SecurityError: storage is disabled");
};

describe("theme store storage", () => {
  it("reads a stored choice", async () => {
    const store = await storeWith({ getItem: (key) => (key === "vocify-theme" ? "dark" : null) });
    assert.equal(store.getThemeMode(), "dark");
  });

  it("follows the system when the stored value is garbage", async () => {
    const store = await storeWith({ getItem: () => "sepia" });
    assert.equal(store.getThemeMode(), "system");
  });

  it("follows the system when storage cannot be read", async () => {
    const store = await storeWith({ getItem: denied, setItem: denied });
    assert.equal(store.getThemeMode(), "system");
  });

  it("keeps a choice for the session when storage cannot be written", async () => {
    const store = await storeWith({ getItem: denied, setItem: denied });
    assert.doesNotThrow(() => store.setThemeMode("dark"));
    assert.equal(store.getThemeMode(), "dark");
  });

  it("writes the choice under vocify-theme", async () => {
    const written: Record<string, string> = {};
    const store = await storeWith({ getItem: () => null, setItem: (key, value) => void (written[key] = value) });
    store.setThemeMode("light");
    assert.deepEqual(written, { "vocify-theme": "light" });
  });
});
