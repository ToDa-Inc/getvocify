import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { homeSendConversation, landingConversation } from "./ask-landing.ts";

describe("landingConversation", () => {
  it("restores only the conversation a ?c= link names, and remembers it only once it has been read", () => {
    assert.deepEqual(landingConversation({ linked: "linked", stored: "stored", restoreStored: false, newId: "new" }), {
      id: "linked",
      fetch: true,
      remember: false,
      fallback: "stored",
    });
  });

  it("falls back to a new id when a dead link arrives in a tab that never used Ask", () => {
    assert.equal(landingConversation({ linked: "dead", stored: null, restoreStored: false, newId: "new" }).fallback, "new");
  });

  it("does not read the tab's last conversation back when the caller asks not to (Inicio without ?c=)", () => {
    assert.deepEqual(landingConversation({ linked: null, stored: "stored", restoreStored: false, newId: "new" }), {
      id: "stored",
      fetch: false,
      remember: false,
      fallback: null,
    });
  });

  it("reads the tab's last conversation back by default (the floating sheet)", () => {
    assert.deepEqual(landingConversation({ linked: null, stored: "stored", restoreStored: true, newId: "new" }), {
      id: "stored",
      fetch: true,
      remember: false,
      fallback: null,
    });
  });

  it("starts and remembers a new id in a tab with no conversation, with nothing to read", () => {
    for (const restoreStored of [true, false]) {
      assert.deepEqual(landingConversation({ linked: null, stored: null, restoreStored, newId: "new" }), {
        id: "new",
        fetch: false,
        remember: true,
        fallback: null,
      });
    }
  });
});

describe("homeSendConversation", () => {
  it("always starts a new conversation from home, even when the current one looks empty", () => {
    let started = 0;
    const fresh = () => {
      started += 1;
      return "fresh";
    };
    assert.equal(homeSendConversation("home", "current", fresh), "fresh");
    assert.equal(started, 1);
  });

  it("keeps the conversation on screen in the chat", () => {
    let started = 0;
    assert.equal(
      homeSendConversation("chat", "current", () => {
        started += 1;
        return "fresh";
      }),
      "current",
    );
    assert.equal(started, 0);
  });
});
