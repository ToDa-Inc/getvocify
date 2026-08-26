import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { callDurationSeconds, formatCallDuration } from './call-duration.ts';

describe('callDurationSeconds', () => {
  it('prefers duration_ms', () => {
    assert.equal(callDurationSeconds({ call_id: '1', title: 'x', has_recording: true, duration_ms: 3800 }), 3.8);
  });

  it('corrects legacy ms stored as duration_seconds', () => {
    assert.equal(
      callDurationSeconds({ call_id: '1', title: 'x', has_recording: true, duration_seconds: 5000 }),
      5,
    );
  });
});

describe('formatCallDuration', () => {
  it('formats short and long durations', () => {
    assert.equal(formatCallDuration(5), '5s');
    assert.equal(formatCallDuration(1000), '16m 40s');
  });
});
