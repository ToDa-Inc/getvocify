import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { humanizeSaasError, isAllowedApiBase, joinApiUrl } from './saas.js';

describe('saas', () => {
  it('joins the production API base to login without dropping /api/v1', () => {
    assert.equal(
      joinApiUrl('https://api.getvocify.com/api/v1', '/auth/login'),
      'https://api.getvocify.com/api/v1/auth/login',
    );
    assert.equal(
      joinApiUrl('https://api.getvocify.com/api/v1/', 'auth/login'),
      'https://api.getvocify.com/api/v1/auth/login',
    );
  });

  it('only allows Vocify SaaS and local API hosts', () => {
    assert.equal(isAllowedApiBase('https://api.getvocify.com/api/v1'), true);
    assert.equal(isAllowedApiBase('http://localhost:8888/api/v1'), true);
    assert.equal(isAllowedApiBase('http://127.0.0.1:8888/api/v1'), true);
    assert.equal(isAllowedApiBase('https://evil.example/api/v1'), false);
    assert.equal(isAllowedApiBase('not a url'), false);
  });

  it('explains renderer Failed to fetch as a CORS/network problem', () => {
    assert.match(
      humanizeSaasError(new TypeError('Failed to fetch')),
      /CORS|could not reach/i,
    );
    assert.equal(
      humanizeSaasError(null, { detail: 'Invalid email or password' }),
      'Invalid email or password',
    );
  });

  it('proxies JSON through fetch so Electron is not subject to renderer CORS', async () => {
    const { proxyJsonRequest } = await import('./saas.js');
    const calls = [];
    const fetchImpl = async (url, opts) => {
      calls.push({ url, opts });
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify({ access_token: 'tok' }),
      };
    };
    const result = await proxyJsonRequest(fetchImpl, {
      base: 'https://api.getvocify.com/api/v1',
      path: '/auth/login',
      method: 'POST',
      body: { email: 'a@b.c', password: 'x' },
    });
    assert.equal(result.ok, true);
    assert.equal(result.data.access_token, 'tok');
    assert.equal(calls[0].url, 'https://api.getvocify.com/api/v1/auth/login');
    assert.equal(calls[0].opts.method, 'POST');
  });
});
