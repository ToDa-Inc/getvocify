import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { NO_TEAM, teamSide } from "./meeting-team.ts";

describe("teamSide", () => {
  it("knows a colleague by whole name, by the start of it, and by first name as the meeting app shows it", () => {
    const team = teamSide(["Toni Mora Botella", "Dani Lopez"], ["Alexander Schlacher"]);
    assert.equal(team.has("Toni Mora Botella"), true);
    assert.equal(team.has("Toni Mora"), true);
    assert.equal(team.has("TONI"), true);
    assert.equal(team.has("tóni"), true);
    assert.equal(team.has("Alexander Schlacher"), false);
    assert.equal(team.has("Mora"), false);
    assert.equal(team.has("Toni García"), false);
    assert.equal(team.has(""), false);
    assert.equal(team.has(null), false);
  });

  it("a colleague whose profile has only a first name is any voice with that first name", () => {
    const team = teamSide(["Toni", "Dani Zal"], ["Alexander Schlacher"]);
    assert.equal(team.has("TONI"), true);
    assert.equal(team.has("Toni Mora"), true);
    assert.equal(team.has("Dani"), true);
    assert.equal(team.has("Dani García"), false);
    assert.equal(team.has("Alexander Schlacher"), false);
    // A guest named like that is the guest: their full name stays theirs, and their first name alone is not enough.
    const shared = teamSide(["Toni"], ["Toni García"]);
    assert.equal(shared.has("Toni García"), false);
    assert.equal(shared.has("Toni"), false);
  });

  it("a guest who shares a colleague's first name keeps that first name on the other side", () => {
    const team = teamSide(["Toni Mora"], ["Toni García"]);
    assert.equal(team.has("Toni"), false);
    assert.equal(team.has("Toni Mora"), true);
    assert.equal(team.has("Toni García"), false);
  });

  it("offers each colleague once and leaves the rep out of the names, though their voice is still the rep's side", () => {
    const team = teamSide(["Toni Mora", " toni mora", "Dani Lopez", ""], [], "Dani López");
    assert.deepEqual(team.names, ["Toni Mora"]);
    assert.equal(team.has("Dani"), true);
  });

  it("changes its key when the team or the guests change, not when the order does", () => {
    assert.equal(teamSide(["A B", "C D"]).key, teamSide(["C D", "A B"]).key);
    assert.notEqual(teamSide(["A B"]).key, teamSide(["A B"], ["A Z"]).key);
    assert.notEqual(teamSide(["A B"]).key, NO_TEAM.key);
  });
});
