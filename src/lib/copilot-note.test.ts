import assert from "node:assert/strict";
import { test } from "node:test";
import { renderCopilotNoteHtml } from "./copilot-note.ts";

test("a note without headings keeps its outcome line apart and its facts as a list", () => {
  const html = renderCopilotNoteHtml(
    '**Resultado:** Rechaza evaluar: el plan ya está definido.\n\n- Country manager en España.\n- Objeción: "todo muy currado".',
  );
  assert.equal(
    html,
    "<p data-note-lead><span>Resultado</span>Rechaza evaluar: el plan ya está definido.</p>" +
      "<ul><li>Country manager en España.</li><li>Objeción: &quot;todo muy currado&quot;.</li></ul>",
  );
});

test("headings, nested bullets and bold still render, and next steps stay out", () => {
  const html = renderCopilotNoteHtml(
    "**Resultado:** Reunión el martes.\n\n### Perfil\n- Sin equipo interno\n  - Venden por distribuidores\n- Decide **Aritzel**\n\n### Próximos pasos\n- Enviar invitación",
  );
  assert.equal(
    html,
    "<p data-note-lead><span>Resultado</span>Reunión el martes.</p><h3>Perfil</h3>" +
      "<ul><li>Sin equipo interno<ul><li>Venden por distribuidores</li></ul></li><li>Decide <strong>Aritzel</strong></li></ul>",
  );
});

test("plain sentences stay paragraphs and markup is escaped", () => {
  assert.equal(renderCopilotNoteHtml("Hablaron del <almacén>.\nLlamar en enero."), "<p>Hablaron del &lt;almacén&gt;.</p><p>Llamar en enero.</p>");
  assert.equal(renderCopilotNoteHtml(""), "");
});
