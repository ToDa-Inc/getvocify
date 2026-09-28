import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { paintBriefBox } from './contact-brief-box.js';

class FakeClassList {
  constructor() { this.names = new Set(); }
  add(name) { this.names.add(name); }
  contains(name) { return this.names.has(name); }
  toggle(name, force) {
    const on = force === undefined ? !this.names.has(name) : Boolean(force);
    if (on) this.names.add(name); else this.names.delete(name);
    return on;
  }
}

class FakeElement {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.textContent = '';
    this.className = '';
    this.hidden = false;
    this.classList = new FakeClassList();
  }
  get childElementCount() { return this.children.length; }
  replaceChildren() { this.children = []; }
  appendChild(child) { this.children.push(child); return child; }
  prepend(child) { this.children.unshift(child); }
}

const doc = { createElement: (tag) => new FakeElement(tag) };

function paint(args) {
  const box = new FakeElement('div');
  const screen = new FakeElement('section');
  const shown = paintBriefBox({ box, screen, flatLines: [], captureActive: false, doc, ...args });
  return { box, screen, shown };
}

describe('contact brief box (extension popup)', () => {
  it('paints the F03 payload exactly as the flat lines, as before brief v2', () => {
    const { box, screen, shown } = paint({
      brief: {
        status: 'ready',
        text: 'Resumen',
        notice: null,
        lines: [
          { type: 'last', text: 'El 2 sep hablasteis del almacén.', source_ref: 'memo-1' },
          { type: 'pending', text: 'Quedó pendiente: enviar el caso.', source_ref: 'memo-1' },
          { type: 'objection', text: 'Objeción: precio.', source_ref: 'memo-1' },
        ],
      },
      flatLines: ['Resumen', 'El 2 sep hablasteis del almacén.', 'Quedó pendiente: enviar el caso.', 'Objeción: precio.'],
    });
    assert.equal(shown, true);
    assert.deepEqual(box.children.map((child) => child.textContent), [
      'Resumen',
      'El 2 sep hablasteis del almacén.',
      'Quedó pendiente: enviar el caso.',
      'Objeción: precio.',
    ]);
    assert.equal(box.hidden, false);
    assert.equal(screen.classList.contains('has-brief'), true);
  });

  it('keeps «Nada pendiente en esta ficha.» for an empty F03 brief', () => {
    const { box, shown } = paint({
      brief: { status: 'ready', text: null, notice: null, lines: [] },
      flatLines: ['Nada pendiente en esta ficha.'],
    });
    assert.equal(shown, true);
    assert.deepEqual(box.children.map((child) => child.textContent), ['Nada pendiente en esta ficha.']);
  });

  it('falls back to the flat lines for an empty v2 brief', () => {
    const { box } = paint({
      brief: { status: 'ready', text: null, notice: null, label: null, lines: [] },
      flatLines: ['Nada pendiente en esta ficha.'],
    });
    assert.deepEqual(box.children.map((child) => child.textContent), ['Nada pendiente en esta ficha.']);
  });

  it('paints the v2 payload with the playbook line and the label chip', () => {
    const { box, screen } = paint({
      brief: {
        status: 'ready',
        text: null,
        notice: null,
        label: 'Pitch hecho · falta cualificar',
        lines: [
          { type: 'hook', text: '11 sep: «se nos quedan leads sin llamar»' },
          { type: 'say', text: 'Precio: compáralo con un comercial más.', source: 'playbook' },
        ],
      },
    });
    assert.equal(box.children.length, 3);
    assert.equal(box.children[1].classList.contains('brief-playbook'), true);
    assert.equal(box.children[2].className, 'v-chip');
    assert.equal(box.children[2].textContent, 'Pitch hecho · falta cualificar');
    assert.equal(screen.classList.contains('has-brief'), true);
  });

  it('paints the company hook after the facts, marked apart', () => {
    const { box } = paint({
      brief: {
        status: 'ready',
        text: null,
        notice: null,
        label: null,
        lines: [
          { type: 'who', text: 'Directora comercial en Factorial' },
          { type: 'company', text: 'En Factorial ya hablaste con Manuel García el 12 sep: Le interesó el fichaje.' },
        ],
      },
    });
    assert.deepEqual(box.children.map((child) => child.textContent), [
      'Directora comercial en Factorial',
      'En Factorial ya hablaste con Manuel García el 12 sep: Le interesó el fichaje.',
    ]);
    assert.equal(box.children[0].classList.contains('brief-company'), false);
    assert.equal(box.children[1].classList.contains('brief-company'), true);
  });

  it('puts the partial notice first', () => {
    const { box } = paint({
      brief: {
        status: 'partial',
        text: 'No se pudo cargar todo.',
        notice: 'No se pudo cargar todo.',
        label: null,
        lines: [{ type: 'hook', text: '11 sep: Hablaron del almacén.' }],
      },
    });
    assert.deepEqual(box.children.map((child) => child.textContent), [
      'No se pudo cargar todo.',
      '11 sep: Hablaron del almacén.',
    ]);
  });

  it('shows the loading line while there is no brief, and hides during capture', () => {
    const loading = paint({ brief: null, flatLines: ['Leyendo…'] });
    assert.deepEqual(loading.box.children.map((child) => child.textContent), ['Leyendo…']);
    assert.equal(loading.screen.classList.contains('has-brief'), true);

    const capturing = paint({
      brief: { status: 'ready', text: null, lines: [{ type: 'last', text: 'x' }] },
      captureActive: true,
    });
    assert.equal(capturing.shown, false);
    assert.equal(capturing.box.hidden, true);
    assert.equal(capturing.screen.classList.contains('has-brief'), false);
  });
});
