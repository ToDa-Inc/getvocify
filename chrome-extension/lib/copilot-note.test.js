import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  parseCopilotNote,
  stripNextStepsSection,
  renderCopilotNoteHtml,
  nextStepsHeadingLabel,
  crmFieldsHeadingLabel,
  htmlToCopilotMarkdown,
} from './copilot-note.js';

const FRANCK = `# Contexto
- Llamada en frío a Franck de NEURTEK para presentar Vocify
- No recordaba haber tenido contacto previo

# Perfil
- No gestiona un equipo comercial interno
  - Las ventas van por distribuidores externos
- Usan Microsoft Dynamics; los distribuidores también

# Decisión
- Franck no es el interlocutor adecuado
- Redirige a **Aritzel Expuru**, director de NEURTEK

# Próximos Pasos
- Contactar a Aritzel Expuru en NEURTEK
`;

describe('parseCopilotNote', () => {
  it('parses headings, bullets, nested bullets, and bold', () => {
    const stripped = stripNextStepsSection(FRANCK);
    const parsed = parseCopilotNote(stripped);
    assert.deepEqual(parsed.sections.map((s) => s.title), ['Contexto', 'Perfil', 'Decisión']);
    assert.equal(parsed.sections[1].items[0].text, 'No gestiona un equipo comercial interno');
    assert.deepEqual(parsed.sections[1].items[0].children, ['Las ventas van por distribuidores externos']);
    assert.match(parsed.sections[2].items[1].text, /Aritzel Expuru/);
  });

  it('strips a trailing próximos pasos heading so tasks are not duplicated', () => {
    const out = stripNextStepsSection(FRANCK);
    assert.equal(/próximos pasos/i.test(out), false);
    assert.match(out, /# Decisión/);
  });
});

describe('renderCopilotNoteHtml', () => {
  it('renders headings and lists without raw hash marks', () => {
    const html = renderCopilotNoteHtml(stripNextStepsSection(FRANCK));
    assert.match(html, /<h3>Contexto<\/h3>/);
    assert.match(html, /<ul>/);
    assert.equal(html.includes('# Contexto'), false);
    assert.match(html, /<strong>Aritzel Expuru<\/strong>/);
  });

  it('does not leave asterisk or plus markers next to list bullets', () => {
    const html = renderCopilotNoteHtml(`# Contexto
* Cold call to Franck
  * Nested point
+ Another item
`);
    assert.match(html, /<li>Cold call to Franck/);
    assert.match(html, /<li>Nested point/);
    assert.match(html, /<li>Another item/);
    assert.equal(html.includes('* Cold call'), false);
    assert.equal(html.includes('* Nested'), false);
    assert.equal(html.includes('+ Another'), false);
  });

  it('falls back to escaped paragraphs for prose summaries', () => {
    const html = renderCopilotNoteHtml('Franck Valls ha aclarado que no gestiona un equipo.');
    assert.match(html, /<p>/);
    assert.equal(html.includes('<h3>'), false);
  });
});

describe('nextStepsHeadingLabel', () => {
  it('uses Spanish when the note is in Spanish', () => {
    assert.equal(nextStepsHeadingLabel(FRANCK), 'Próximos pasos');
  });

  it('uses English when the note is in English', () => {
    assert.equal(nextStepsHeadingLabel('# Context\n- Cold call to Frank'), 'Next steps');
  });
});

describe('crmFieldsHeadingLabel', () => {
  it('stays Fields even when the note is in Spanish', () => {
    assert.equal(crmFieldsHeadingLabel(FRANCK), 'Fields');
    assert.equal(crmFieldsHeadingLabel('# Context\n- Cold call to Frank'), 'Fields');
  });
});

describe('htmlToCopilotMarkdown', () => {
  it('roundtrips rendered note HTML without showing hash marks to edit', () => {
    const html = renderCopilotNoteHtml(stripNextStepsSection(FRANCK));
    const md = htmlToCopilotMarkdown(html);
    assert.equal(md.includes('##'), false);
    assert.match(md, /^# Contexto/m);
    assert.match(md, /# Perfil/);
    assert.match(md, /- No gestiona un equipo comercial interno/);
    assert.match(md, / {2}- Las ventas van por distribuidores externos/);
    assert.match(md, /\*\*Aritzel Expuru\*\*/);
  });

  it('reads through a contenteditable wrapper div', () => {
    const md = htmlToCopilotMarkdown(
      '<div><h3>Contexto</h3><ul><li>Cold call</li></ul></div>',
    );
    assert.equal(md, '# Contexto\n- Cold call');
  });
});
