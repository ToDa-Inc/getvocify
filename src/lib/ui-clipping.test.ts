import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { MENU_TOKENS } from "./theme/tokens.ts";

const source = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

describe("nothing in a panel can be cut off", () => {
  it("a menu or popover scrolls inside the room it has, instead of clipping its content", () => {
    assert.match(MENU_TOKENS.surface, /overflow-y-auto/);
    assert.match(MENU_TOKENS.surface, /max-h-\[var\(--radix-popper-available-height\)\]/);
    assert.doesNotMatch(MENU_TOKENS.surface, /overflow-hidden/);
  });

  it("popovers and menus keep a margin to the screen edge", () => {
    assert.match(source("../components/ui/popover.tsx"), /collisionPadding/);
    assert.match(source("../components/ui/dropdown-menu.tsx"), /collisionPadding/);
  });

  it("tooltips render in a portal, so no overflow-hidden parent can cut them off", () => {
    assert.match(source("../components/ui/tooltip.tsx"), /TooltipPrimitive\.Portal/);
  });

  it("a segmented row wraps in a narrow panel instead of pushing options outside it", () => {
    const segmented = source("../components/ui/segmented.tsx");
    assert.doesNotMatch(segmented, /flex-nowrap/);
    assert.match(source("./theme/tokens.ts"), /segmentList:\s*"[^"]*flex-wrap/);
  });
});
