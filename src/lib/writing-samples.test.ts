import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { productCatalog } from "./product-catalog.ts";
import {
  MAX_CHARS,
  MAX_SAMPLES,
  countLabel,
  isDirty,
  samplesPayload,
  slotsFor,
  tooShort,
} from "./writing-samples.ts";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const settingsSource = read("../components/dashboard/settings/WritingSamplesSettings.tsx");
const sectionSource = read("../pages/dashboard/settings/BriefHighlightSection.tsx");
const apiSource = read("./api/writing-samples.ts");
const LONG = "Hola Nuria, te paso el resumen de lo que vimos ayer con el equipo.";

describe("writing samples", () => {
  it("sends trimmed samples and drops the empty boxes", () => {
    assert.deepEqual(samplesPayload([`  ${LONG}  `, "", "   "]), [LONG]);
    assert.deepEqual(samplesPayload(["", "", ""]), []);
  });

  it("always shows three boxes, filled with what is saved", () => {
    assert.equal(MAX_SAMPLES, 3);
    assert.deepEqual(slotsFor([]), ["", "", ""]);
    assert.deepEqual(slotsFor([LONG]), [LONG, "", ""]);
    assert.deepEqual(slotsFor([LONG, LONG, LONG, LONG]), [LONG, LONG, LONG]);
  });

  it("flags a filled sample under 40 characters and ignores empty boxes", () => {
    assert.equal(tooShort([LONG, "", "  "]), false);
    assert.equal(tooShort([LONG, "Gracias, Marta"]), true);
    assert.equal(tooShort([`  ${"a".repeat(39)}  `]), true);
    assert.equal(tooShort(["a".repeat(40)]), false);
  });

  it("is dirty only when the trimmed samples differ from the saved ones", () => {
    assert.equal(isDirty([`${LONG} `, "", ""], [LONG]), false);
    assert.equal(isDirty(["", "", ""], [LONG]), true);
    assert.equal(isDirty([LONG, LONG, ""], [LONG]), true);
    assert.equal(isDirty(["", "", ""], []), false);
  });

  it("shows the count in the header only when pasted samples exist", () => {
    const es = productCatalog.ES;
    assert.equal(countLabel(0, es.writingSamplesCountOne, es.writingSamplesCountMany), null);
    assert.equal(countLabel(1, es.writingSamplesCountOne, es.writingSamplesCountMany), "1 ejemplo");
    assert.equal(countLabel(2, es.writingSamplesCountOne, es.writingSamplesCountMany), "2 ejemplos");
  });

  it("has the copy in both languages, with the brief's helper line", () => {
    assert.equal(productCatalog.ES.writingSamplesHeading, "Tu forma de escribir");
    assert.equal(
      productCatalog.ES.writingSamplesHelper,
      "Pega hasta 3 emails tuyos para que el borrador suene a ti.",
    );
    assert.equal(productCatalog.EN.writingSamplesCountMany.includes("{count}"), true);
    assert.equal(productCatalog.ES.writingSamplesCountMany.includes("{count}"), true);
  });

  it("is a collapsed block below the summary preference, not a new tab", () => {
    assert.match(settingsSource, /<Collapsible\b/);
    assert.doesNotMatch(settingsSource, /defaultOpen|open=\{true\}/);
    assert.match(settingsSource, /maxLength=\{MAX_CHARS\}/);
    assert.equal(MAX_CHARS, 1500);
    const brief = sectionSource.indexOf("<BriefHighlightSettings />");
    const samples = sectionSource.indexOf("<WritingSamplesSettings />");
    assert.ok(brief >= 0 && samples > brief, "WritingSamplesSettings renders below BriefHighlightSettings");
  });

  it("loads and saves through the rep's endpoint with loading and error states", () => {
    assert.match(apiSource, /api\.get<[^>]+>\("\/writing-samples"\)/);
    assert.match(apiSource, /api\.put<[^>]+>\("\/writing-samples"/);
    assert.match(settingsSource, /isLoading \? \(\s*<div[^>]*>\s*<VocifySpinner/);
    assert.match(settingsSource, /isError \? \(\s*<p[^>]*>\{t\.product\.writingSamplesLoadFailed\}/);
    assert.match(settingsSource, /writingSamplesSaveFailed/);
    assert.match(settingsSource, /save\.mutate\(samplesPayload\(drafts\)\)/);
    assert.match(settingsSource, /disabled=\{!dirty \|\| short \|\| save\.isPending\}/);
    assert.match(settingsSource, /rounded-full bg-beige text-cream px-6 text-\[10px\] font-medium/);
  });
});
