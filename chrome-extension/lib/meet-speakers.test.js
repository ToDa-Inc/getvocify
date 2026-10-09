import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { cleanName, isMeetCallPath, readMeetTiles, speakingNames } from './meet-speakers.js';

/** Just enough DOM for the reader: [attr], .class and tag.class selectors. */
function el(tag, { attrs = {}, classes = [], text = '', children = [] } = {}) {
  const node = {
    tag,
    children,
    classList: { contains: (c) => classes.includes(c) },
    getAttribute: (a) => (a in attrs ? attrs[a] : null),
    hasAttribute: (a) => a in attrs,
    get textContent() {
      return text + children.map((c) => c.textContent).join('');
    },
    matches(sel) {
      const attr = sel.match(/^\[([\w-]+)\]$/);
      if (attr) return attr[1] in attrs;
      const [t, cls] = sel.split('.');
      return (!t || t === tag) && classes.includes(cls);
    },
    querySelectorAll(sel) {
      return children.flatMap((c) => [...(c.matches(sel) ? [c] : []), ...c.querySelectorAll(sel)]);
    },
    querySelector(sel) {
      return node.querySelectorAll(sel)[0] ?? null;
    },
  };
  return node;
}

function tile(id, name, { speakingClass, self = false } = {}) {
  return el('div', {
    attrs: { 'data-participant-id': id, ...(self ? { 'data-self-name': name } : {}) },
    children: [
      el('span', { classes: ['notranslate'], text: name }),
      el('div', { classes: ['DYfzY', 'cYKTje', ...(speakingClass ? [speakingClass] : [])] }),
    ],
  });
}

describe('Meet speaker reading', () => {
  it('names the remote people Meet shows speaking, not you', () => {
    const page = el('body', {
      children: [
        tile('spaces/a/devices/1', 'Dani', { speakingClass: 'HX2H7', self: true }),
        tile('spaces/a/devices/2', 'Marta García', { speakingClass: 'HX2H7' }),
        tile('spaces/a/devices/3', 'Juan'),
      ],
    });
    assert.deepEqual(speakingNames(readMeetTiles(page)), ['Marta García']);
  });

  it('a muted tile (indicator without a speaking class) is not speaking', () => {
    const page = el('body', { children: [tile('p1', 'Marta')] });
    assert.deepEqual(readMeetTiles(page), [{ name: 'Marta', self: false, speaking: false }]);
  });

  it('reads each tile once, and two speaking at once both count', () => {
    const page = el('body', {
      children: [
        tile('p1', 'Marta', { speakingClass: 'Oaajhc' }),
        tile('p1', 'Marta', { speakingClass: 'Oaajhc' }),
        tile('p2', 'Ana', { speakingClass: 'OgVli' }),
      ],
    });
    assert.deepEqual(speakingNames(readMeetTiles(page)), ['Ana', 'Marta']);
  });

  it('drops placeholder names', () => {
    assert.equal(cleanName('Google Participant (spaces/x)'), null);
    assert.equal(cleanName('  Marta   García '), 'Marta García');
    assert.equal(cleanName('M'), null);
  });

  it('knows a call address', () => {
    assert.equal(isMeetCallPath('/abc-defg-hij'), true);
    assert.equal(isMeetCallPath('/landing'), false);
    assert.equal(isMeetCallPath('/'), false);
  });
});
