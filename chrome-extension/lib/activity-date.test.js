import assert from 'node:assert/strict';
import {
  formatActivityTimestamp,
  parseActivityTimestamp,
  activityTimestampFromRecording,
} from './activity-date.js';

assert.equal(formatActivityTimestamp('2026-08-19T13:35:00.000Z').includes('Aug'), true);
assert.equal(formatActivityTimestamp('2026-08-19T13:35:00.000Z').includes(','), true);
assert.equal(formatActivityTimestamp(null), '');
assert.equal(parseActivityTimestamp(1_700_000_000_000)?.getTime(), 1_700_000_000_000);
assert.equal(activityTimestampFromRecording({ timestamp_ms: 1_700_000_000_000 }), 1_700_000_000_000);

console.log('activity-date.test.js ok');
