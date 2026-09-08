import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { vocifyCallHeaders } from './telnyx-headers.js';

describe('vocifyCallHeaders', () => {
  it('returns no headers when every id is missing', () => {
    assert.deepEqual(vocifyCallHeaders({}), []);
  });

  it('emits caller, contact, and deal headers in that order', () => {
    assert.deepEqual(
      vocifyCallHeaders({
        callerId: '+34600111222',
        contactId: 'c1',
        dealId: 'd1',
      }),
      [
        { name: 'X-Vocify-Caller-Id', value: '+34600111222' },
        { name: 'X-Vocify-Contact-Id', value: 'c1' },
        { name: 'X-Vocify-Deal-Id', value: 'd1' },
      ],
    );
  });

  it('omits blank fields and stringifies numeric ids', () => {
    assert.deepEqual(
      vocifyCallHeaders({ callerId: '', contactId: 42, dealId: null }),
      [{ name: 'X-Vocify-Contact-Id', value: '42' }],
    );
  });
});
