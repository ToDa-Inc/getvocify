import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { planRecordingsFetch, planRecordingsResult } from './recordings-fetch.js';

describe('planRecordingsFetch', () => {
  it('fetches inbox on first visit (no cache, nothing in flight)', () => {
    assert.equal(
      planRecordingsFetch({ scopeKey: 'inbox' }).action,
      'fetch',
    );
  });

  it('does not start a second inbox request while one is in flight', () => {
    assert.equal(
      planRecordingsFetch({
        scopeKey: 'inbox',
        inFlightKey: 'inbox',
        loading: true,
      }).action,
      'skip',
    );
  });

  it('skips inbox after a completed fetch', () => {
    assert.equal(
      planRecordingsFetch({
        scopeKey: 'inbox',
        cacheKey: 'inbox',
        loading: false,
      }).action,
      'skip',
    );
  });

  it('retries inbox when the spinner is on but nothing is in flight', () => {
    // Today's hang: cache key was set when the request *started*, the result
    // was dropped, and skipBroadcast never invalidates inbox — so GET_STATE
    // after login/me/memos never hits /crm/hubspot/recordings again.
    assert.equal(
      planRecordingsFetch({
        scopeKey: 'inbox',
        cacheKey: 'inbox',
        inFlightKey: null,
        loading: true,
      }).action,
      'fetch',
    );
  });

  it('fetches when the page scope changed', () => {
    assert.equal(
      planRecordingsFetch({
        scopeKey: 'inbox',
        cacheKey: 'deal:D1',
        loading: false,
      }).action,
      'fetch',
    );
  });

  it('force-refetches even when the same scope is cached', () => {
    assert.equal(
      planRecordingsFetch({
        scopeKey: 'deal:D1',
        cacheKey: 'deal:D1',
        force: true,
      }).action,
      'fetch',
    );
  });
});

describe('planRecordingsResult', () => {
  it('applies when this generation still matches the current inbox', () => {
    assert.equal(
      planRecordingsResult({
        gen: 1,
        fetchGen: 1,
        resultScopeKey: 'inbox',
        currentScopeKey: 'inbox',
      }).action,
      'apply',
    );
  });

  it('ignores a stale generation so a newer fetch can own the spinner', () => {
    assert.equal(
      planRecordingsResult({
        gen: 1,
        fetchGen: 2,
        resultScopeKey: 'inbox',
        currentScopeKey: 'inbox',
      }).action,
      'ignore',
    );
  });

  it('abandons when the page left this scope — must clear the spinner', () => {
    assert.equal(
      planRecordingsResult({
        gen: 3,
        fetchGen: 3,
        resultScopeKey: 'inbox',
        currentScopeKey: 'deal:D1',
      }).action,
      'abandon',
    );
  });
});
