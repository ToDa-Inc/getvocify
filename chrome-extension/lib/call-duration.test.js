import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { callDurationSeconds, formatCallDuration } from './call-duration.js';

describe('callDurationSeconds', () => {
  it('uses duration_ms from HubSpot', () => {
    assert.equal(callDurationSeconds({ duration_ms: 5000, duration_seconds: 5000 }), 5);
    assert.equal(callDurationSeconds({ duration_ms: 3800 }), 3.8);
  });

  it('does not treat a 5s call as 83 minutes when duration_ms is missing', () => {
    assert.equal(callDurationSeconds({ duration_seconds: 5000 }), 5);
    assert.equal(formatCallDuration(callDurationSeconds({ duration_seconds: 5000 })), '5s');
  });

  it('keeps a converted 16m 40s call', () => {
    assert.equal(callDurationSeconds({ duration_seconds: 1000 }), 1000);
    assert.equal(formatCallDuration(1000), '16m 40s');
  });
});
