import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  buildCopilotChecklistRequestBody,
  fetchCopilotChecklist,
} from './copilot-checklist.js';

describe('copilot checklist client', () => {
  it('sends meeting mode and capture_id only when the session has one', () => {
    assert.deepEqual(buildCopilotChecklistRequestBody({ session: { callMode: 'meeting' } }), {
      call_mode: 'meeting',
    });
    assert.deepEqual(
      buildCopilotChecklistRequestBody({ session: { capture_id: 'cap-9' } }),
      { call_mode: 'meeting', capture_id: 'cap-9' },
    );
  });

  it('returns parsed JSON without calling a live API', async () => {
    let url = '';
    let init;
    const fetchImpl = async (u, options) => {
      url = u;
      init = options;
      return {
        ok: true,
        status: 200,
        json: async () => ({ observed: 0, applicable: 2, steps: [] }),
      };
    };
    const result = await fetchCopilotChecklist(fetchImpl, {
      apiBase: 'https://example.test/api/v1',
      token: 'tok',
      body: { call_mode: 'meeting' },
    });
    assert.equal(url, 'https://example.test/api/v1/copilot/checklist');
    assert.equal(init.headers.Authorization, 'Bearer tok');
    assert.equal(result.ok, true);
    assert.equal(result.data.applicable, 2);
  });
});
