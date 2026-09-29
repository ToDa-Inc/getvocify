import assert from "node:assert/strict";
import test from "node:test";
import { parseBlocks, parseInline } from "./ask-markdown.ts";

test("inline bold, code and citations become tokens, never HTML", () => {
  assert.deepEqual(parseInline("**Marina** dijo `caro` [1]"), [
    { t: "bold", v: "Marina" },
    { t: "text", v: " dijo " },
    { t: "code", v: "caro" },
    { t: "text", v: " " },
    { t: "cite", n: 1 },
  ]);
  assert.deepEqual(parseInline("<b>x</b>"), [{ t: "text", v: "<b>x</b>" }]);
});

test("bullets and numbered lists group into one block each", () => {
  const blocks = parseBlocks("Resumen\n\n- uno\n- dos\n\n1. a\n2. b");
  assert.deepEqual(blocks.map((b) => b.t), ["p", "ul", "ol"]);
  assert.equal((blocks[1] as { items: unknown[] }).items.length, 2);
});

test("a pipe table needs its separator row", () => {
  const table = parseBlocks("| Cat | N |\n| --- | --- |\n| Precio | 9 |\n| Timing | 2 |");
  assert.equal(table[0].t, "table");
  assert.equal((table[0] as { rows: unknown[] }).rows.length, 2);
  assert.equal(parseBlocks("| solo | una |")[0].t, "p");
});

test("headings are flattened to bold text", () => {
  const [p] = parseBlocks("## Resultado");
  assert.deepEqual(p, { t: "p", inline: [{ t: "bold", v: "Resultado" }] });
});

test("empty input has no blocks", () => {
  assert.deepEqual(parseBlocks("  \n "), []);
});

test("a markdown link to an http(s) address becomes a link; anything else stays text", () => {
  const nodes = parseInline("Abre [la ficha](https://app.hubspot.com/contacts/1) y mira [1].");
  assert.deepEqual(nodes.filter((n) => n.t === "link"), [{ t: "link", label: "la ficha", href: "https://app.hubspot.com/contacts/1" }]);
  assert.ok(nodes.some((n) => n.t === "cite" && n.n === 1));
  assert.deepEqual(parseInline("[x](javascript:alert(1))").filter((n) => n.t === "link"), []);
});
