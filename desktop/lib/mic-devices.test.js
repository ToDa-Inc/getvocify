import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { TAP_DEVICE_NAME, isTapDevice, pickMicConstraints } from './mic-devices.js';

describe('mic-devices', () => {
  it('never selects the Vocify tap as the sales microphone', () => {
    assert.equal(isTapDevice(`${TAP_DEVICE_NAME} (Aggregate)`), true);
    const constraints = pickMicConstraints([
      { kind: 'audioinput', deviceId: 'tap', label: TAP_DEVICE_NAME },
      { kind: 'audioinput', deviceId: 'built-in', label: 'MacBook Pro Microphone' },
    ]);
    assert.deepEqual(constraints.audio.deviceId, { exact: 'built-in' });
  });

  it('falls back to default audio when no labeled inputs exist', () => {
    assert.deepEqual(pickMicConstraints([]), { audio: true, video: false });
  });
});
