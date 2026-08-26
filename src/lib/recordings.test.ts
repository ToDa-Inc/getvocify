import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  getRecordingAction,
  getMemoStatusPill,
  recordingsNeedPoll,
} from './recordings.ts';

describe('getRecordingAction', () => {
  it('offers transcribe when there is no memo yet', () => {
    const action = getRecordingAction({
      call_id: '1',
      title: 'Call',
      has_recording: true,
      memo_id: null,
      memo_status: null,
    });
    assert.deepEqual(action, { label: 'Transcribe', action: 'transcribe' });
  });

  it('offers continue when memo is pending review', () => {
    const action = getRecordingAction({
      call_id: '1',
      title: 'Call',
      has_recording: true,
      memo_id: 'm1',
      memo_status: 'pending_review',
    });
    assert.deepEqual(action, { label: 'Continue', action: 'continue', memoId: 'm1' });
  });

  it('hides action while transcribing', () => {
    const action = getRecordingAction({
      call_id: '1',
      title: 'Call',
      has_recording: true,
      memo_id: 'm1',
      memo_status: 'transcribing',
    });
    assert.equal(action, null);
  });
});

describe('getMemoStatusPill', () => {
  it('shows busy label while extracting', () => {
    const pill = getMemoStatusPill({
      call_id: '1',
      title: 'Call',
      has_recording: true,
      memo_id: 'm1',
      memo_status: 'extracting',
    });
    assert.deepEqual(pill, { variant: 'processing', text: 'Extracting', busy: true });
  });
});

describe('recordingsNeedPoll', () => {
  it('polls when any recording is still processing', () => {
    assert.equal(
      recordingsNeedPoll([
        { call_id: '1', title: 'A', has_recording: true, memo_status: 'transcribing' },
        { call_id: '2', title: 'B', has_recording: true, memo_status: 'approved' },
      ]),
      true,
    );
    assert.equal(
      recordingsNeedPoll([
        { call_id: '1', title: 'A', has_recording: true, memo_status: 'approved' },
      ]),
      false,
    );
  });
});
