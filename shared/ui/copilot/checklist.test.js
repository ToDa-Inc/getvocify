import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { overlayChecklistMarkup } from "./checklist.js";
import { renderToString } from "../html.js";
import { strings } from "../i18n.js";

const sample = {
  playbook_version_id: "pb-1",
  observed: 1,
  applicable: 3,
  steps: [
    { step_id: "s1", label: "Saludo", status: "met", evidence_refs: ["ev-1"] },
    { step_id: "s2", label: "Precio", status: "pending", evidence_refs: [] },
  ],
};

describe("overlay checklist renderer", () => {
  it("renders nothing for calls, empty applicable, or missing payload", () => {
    assert.equal(overlayChecklistMarkup(sample, { kind: "call" }), null);
    assert.equal(overlayChecklistMarkup({ ...sample, applicable: 0 }, { kind: "meeting" }), null);
    assert.equal(overlayChecklistMarkup(null, { kind: "meeting" }), null);
  });

  it("shows progress and step labels without evidence text", () => {
    const es = strings("es");
    const html = overlayChecklistMarkup(sample, {
      kind: "meeting",
      doneLabel: es.checklistDone,
      progressLabel: es.checklistProgress,
    });
    const out = renderToString(html);
    assert.match(out, /1 de 3/);
    assert.match(out, /Saludo/);
    assert.match(out, /Hecho/);
    assert.match(out, /Precio/);
    assert.doesNotMatch(out, /ev-1/);

    const en = strings("en");
    const enOut = renderToString(
      overlayChecklistMarkup(sample, {
        kind: "meeting",
        doneLabel: en.checklistDone,
        progressLabel: en.checklistProgress,
      }),
    );
    assert.match(enOut, /1 of 3/);
    assert.match(enOut, /Done/);
  });
});
