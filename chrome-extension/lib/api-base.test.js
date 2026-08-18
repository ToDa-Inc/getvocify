import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  LOCAL_API_BASE,
  PROD_API_BASE,
  apiBaseToWsOrigin,
  isUnpackedExtension,
  resolveApiBase,
} from './api-base.js';

describe('isUnpackedExtension', () => {
  it('treats Load unpacked as local (no update_url)', () => {
    assert.equal(isUnpackedExtension({ name: 'Vocify' }), true);
  });

  it('treats store/packed builds as production', () => {
    assert.equal(
      isUnpackedExtension({ name: 'Vocify', update_url: 'https://clients2.google.com/service/update2/crx' }),
      false,
    );
  });
});

describe('resolveApiBase', () => {
  it('uses localhost for unpacked extensions', () => {
    assert.equal(resolveApiBase({ unpacked: true }), LOCAL_API_BASE);
  });

  it('uses production for packed extensions', () => {
    assert.equal(resolveApiBase({ unpacked: false }), PROD_API_BASE);
  });

  it('lets chrome.storage api_base override either default', () => {
    assert.equal(
      resolveApiBase({ unpacked: true, override: 'https://api.getvocify.com/api/v1/' }),
      PROD_API_BASE,
    );
    assert.equal(
      resolveApiBase({ unpacked: false, override: 'http://localhost:8888/api/v1' }),
      LOCAL_API_BASE,
    );
  });
});

describe('apiBaseToWsOrigin', () => {
  it('maps local http API to ws origin', () => {
    assert.equal(apiBaseToWsOrigin(LOCAL_API_BASE), 'ws://localhost:8888');
  });

  it('maps production https API to wss origin', () => {
    assert.equal(apiBaseToWsOrigin(PROD_API_BASE), 'wss://api.getvocify.com');
  });
});
