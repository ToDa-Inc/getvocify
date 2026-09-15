import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  activityFilterChips,
  authorChipLabel,
  authorDisplayName,
  canViewCompanyActivity,
  defaultActivityAuthorId,
  filterByAuthor,
  shouldShowActivityAuthorFilter,
} from "./activity-authors.ts";

describe("activity authors", () => {
  it("limits company-wide lists to owner and admin", () => {
    assert.equal(canViewCompanyActivity("owner"), true);
    assert.equal(canViewCompanyActivity("admin"), true);
    assert.equal(canViewCompanyActivity("member"), false);
  });

  it("labels the current user as You", () => {
    assert.equal(authorChipLabel("Ada", "u1", "u1"), "You");
    assert.equal(authorChipLabel("Ada", "u2", "u1"), "Ada");
    assert.equal(authorChipLabel(null, null, "u1"), null);
  });

  it("falls back from name to email prefix", () => {
    assert.equal(authorDisplayName("Ada Vale", "ada@acme.com"), "Ada Vale");
    assert.equal(authorDisplayName(" ", "ada@acme.com"), "ada");
  });

  it("filters lists by author", () => {
    const rows = [
      { id: "a", userId: "u1" },
      { id: "b", userId: "u2" },
    ];
    assert.deepEqual(
      filterByAuthor(rows, "u2", (row) => row.userId).map((row) => row.id),
      ["b"],
    );
    assert.equal(filterByAuthor(rows, null, (row) => row.userId).length, 2);
  });

  it("defaults owners and admins to their own activity when the filter is visible", () => {
    assert.equal(defaultActivityAuthorId(true, "u1", 2), "u1");
    assert.equal(defaultActivityAuthorId(false, "u1", 2), null);
    assert.equal(defaultActivityAuthorId(true, null, 2), null);
  });

  it("does not default Mine when the author filter is hidden", () => {
    assert.equal(defaultActivityAuthorId(true, "u1", 1), null);
    assert.equal(defaultActivityAuthorId(true, "u1", 0), null);
  });

  it("shows the author filter for solo owners and admins", () => {
    assert.equal(shouldShowActivityAuthorFilter(true, "u1"), true);
    assert.equal(shouldShowActivityAuthorFilter(false, "u1"), false);
    assert.equal(shouldShowActivityAuthorFilter(true, null), false);
  });

  it("offers Mine and All chips for a solo owner", () => {
    const chips = activityFilterChips([], "u1");
    assert.deepEqual(
      chips.map((chip) => chip.label),
      ["Mine", "All"],
    );
  });

  it("orders filter chips Mine then All then teammates", () => {
    const chips = activityFilterChips(
      [
        { userId: "u1", label: "Ada" },
        { userId: "u2", label: "Bob" },
      ],
      "u1",
    );
    assert.deepEqual(
      chips.map((chip) => chip.label),
      ["Mine", "All", "Bob"],
    );
    assert.equal(chips[0].id, "u1");
    assert.equal(chips[1].id, null);
  });
});
