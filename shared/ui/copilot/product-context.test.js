import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  LEGACY_DEFAULT_PRODUCT_CONTEXT,
  resolveProductContextForSuggest,
} from './product-context.js';

describe('resolveProductContextForSuggest', () => {
  it('prefers non-blank local text over profile', () => {
    assert.equal(
      resolveProductContextForSuggest('We sell field analytics.', 'Profile offer'),
      'We sell field analytics.',
    );
  });

  it('uses profile when local is blank', () => {
    assert.equal(
      resolveProductContextForSuggest('   ', 'Profile offer'),
      'Profile offer',
    );
    assert.equal(resolveProductContextForSuggest('', 'Profile offer'), 'Profile offer');
  });

  it('omits when both local and profile are blank', () => {
    assert.equal(resolveProductContextForSuggest('', ''), '');
    assert.equal(resolveProductContextForSuggest('  ', null), '');
  });

  it('does not let legacy Vocify pitch win over profile', () => {
    assert.equal(
      resolveProductContextForSuggest(LEGACY_DEFAULT_PRODUCT_CONTEXT, 'Real company offer'),
      'Real company offer',
    );
  });
});
