import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  LEGACY_DEFAULT_PRODUCT_CONTEXT,
  buildCopilotSuggestRequestBody,
  shouldRunCopilotSuggest,
} from './copilot-suggest-body.js';

const productContext = 'Product context';

describe('shouldRunCopilotSuggest', () => {
  it('skips fetch when live help is off or not a meeting', () => {
    assert.equal(shouldRunCopilotSuggest({ assistEnabled: false, callMode: 'meeting' }), false);
    assert.equal(shouldRunCopilotSuggest({ assistEnabled: true, callMode: 'call' }), false);
    assert.equal(shouldRunCopilotSuggest({ assistEnabled: true, callMode: 'meeting' }), true);
  });
});

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

  it('omits product_context for legacy default pitch; keeps custom text', () => {
    const legacyBody = buildCopilotSuggestRequestBody({
      callMode: 'meeting',
      latestTurn: 'hello',
      transcriptWindow: 'They: hello',
      productContext: LEGACY_DEFAULT_PRODUCT_CONTEXT,
    });
    assert.ok(legacyBody);
    assert.equal('product_context' in legacyBody, false);

    const custom = 'We sell analytics for field sales teams.';
    const customBody = buildCopilotSuggestRequestBody({
      callMode: 'meeting',
      latestTurn: 'hello',
      transcriptWindow: 'They: hello',
      productContext: custom,
    });
    assert.ok(customBody);
    assert.equal(customBody.product_context, custom);
  });
});
