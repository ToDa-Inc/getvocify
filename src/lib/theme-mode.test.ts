import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { THEME_STORAGE_KEY, parseThemeMode, resolveTheme } from "./theme-mode.ts";

describe("parseThemeMode", () => {
  it("keeps the three valid choices", () => {
    assert.equal(parseThemeMode("light"), "light");
    assert.equal(parseThemeMode("dark"), "dark");
    assert.equal(parseThemeMode("system"), "system");
  });

  it("falls back to system when nothing is stored", () => {
    assert.equal(parseThemeMode(null), "system");
    assert.equal(parseThemeMode(undefined), "system");
  });

  it("falls back to system for a garbage string", () => {
    assert.equal(parseThemeMode("purple"), "system");
    assert.equal(parseThemeMode(""), "system");
    assert.equal(parseThemeMode("Dark"), "system");
  });

  it("falls back to system for anything that is not a string", () => {
    assert.equal(parseThemeMode(1), "system");
    assert.equal(parseThemeMode(true), "system");
    assert.equal(parseThemeMode({ mode: "dark" }), "system");
  });
});

describe("resolveTheme", () => {
  it("an explicit choice wins over the system preference", () => {
    assert.equal(resolveTheme("light", true), "light");
    assert.equal(resolveTheme("dark", false), "dark");
  });

  it("system follows the system preference", () => {
    assert.equal(resolveTheme("system", true), "dark");
    assert.equal(resolveTheme("system", false), "light");
  });
});

describe("THEME_STORAGE_KEY", () => {
  it("is vocify-theme", () => {
    assert.equal(THEME_STORAGE_KEY, "vocify-theme");
  });
});
