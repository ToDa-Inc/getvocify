import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { noteRows, notesRequestPath } from './notes-list.js';

describe('notes list', () => {
  const now = Date.parse('2026-09-24T12:00:00Z');
  it('titles a memo by contact, then company, then a meaningful fallback', () => {
    const rows = noteRows([
      { id: 'a', createdAt: '2026-09-24T10:00:00Z', audioDuration: 1800, status: 'approved', extraction: { contactName: 'Ana Ruiz' } },
      { id: 'b', createdAt: '2026-09-23T09:00:00Z', audioDuration: 60, status: 'pending_review', extraction: { companyName: 'Acme' } },
      { id: 'c', createdAt: '2026-09-20T09:05:00Z', audioDuration: 0, status: 'extracting', extraction: null },
    ], { now, lang: 'es' });
    assert.equal(rows[0].title, 'Ana Ruiz');
    assert.equal(rows[1].title, 'Acme');
    assert.equal(rows[2].title, 'Reunión sin título');
    assert.equal(rows[0].minutes, 30);
    assert.equal(rows[1].pending, true);
    assert.equal(rows[0].pending, false);
  });
  it('reads the latest 50 memos', () => {
    assert.equal(notesRequestPath(), '/memos?limit=50');
  });
});
