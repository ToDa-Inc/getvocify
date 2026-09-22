import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { buildCopilotSuggestRequestBody } from './copilot-suggest-body.js';

const productContext = 'Product context';

describe('buildCopilotSuggestRequestBody', () => {
  it('meeting + contact record sends contact_id', () => {
    const body = buildCopilotSuggestRequestBody({
      callMode: 'meeting',
      context: { objectType: 'contact', recordId: '12345' },
      latestTurn: 'hello',
      transcriptWindow: 'They: hello',
      productContext,
    });
    assert.ok(body);
    assert.equal(body.call_mode, 'meeting');
    assert.equal(body.contact_id, '12345');
  });

  it('meeting + deal omits contact_id', () => {
    const body = buildCopilotSuggestRequestBody({
      callMode: 'meeting',
      context: { objectType: 'deal', recordId: '999' },
      latestTurn: 'hello',
      transcriptWindow: 'They: hello',
      productContext,
    });
    assert.ok(body);
    assert.equal(body.call_mode, 'meeting');
    assert.equal('contact_id' in body, false);
  });

  it('callMode call returns null', () => {
    const body = buildCopilotSuggestRequestBody({
      callMode: 'call',
      context: { objectType: 'contact', recordId: '12345' },
      latestTurn: 'hello',
      transcriptWindow: 'They: hello',
      productContext,
    });
    assert.equal(body, null);
  });

  it('omits product_context when blank', () => {
    const body = buildCopilotSuggestRequestBody({
      callMode: 'meeting',
      latestTurn: 'hello',
      transcriptWindow: 'They: hello',
      productContext: '   ',
    });
    assert.ok(body);
    assert.equal('product_context' in body, false);
  });

  it('includes product_context when non-empty', () => {
    const body = buildCopilotSuggestRequestBody({
      callMode: 'meeting',
      latestTurn: 'hello',
      transcriptWindow: 'They: hello',
      productContext,
    });
    assert.ok(body);
    assert.equal(body.product_context, productContext);
  });
});
