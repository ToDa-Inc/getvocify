import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  getRecordingAction,
  getMemoStatusPill,
  recordingsNeedPoll,
} from './recordings.ts';
import { recordingListTitle } from './copilot-note.ts';

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

describe('recordingListTitle', () => {
  it('keeps a meaningful HubSpot title', () => {
    assert.equal(
      recordingListTitle({ title: 'Llamada con Ignacio Montoya', to_number: null, from_number: null }),
      'Llamada con Ignacio Montoya',
    );
  });

  it('uses memo contact name when HubSpot title is generic', () => {
    assert.equal(
      recordingListTitle(
        { title: 'Llamada Vocify', to_number: '+34600000000', from_number: null },
        { extraction: { contactName: 'Bimal Melwani', companyName: 'Acme' } },
      ),
      'Bimal Melwani',
    );
  });

  it('falls back to phone when no memo identity exists', () => {
    assert.equal(
      recordingListTitle({
        title: 'Llamada Vocify',
        to_number: '+34669701069',
        from_number: null,
      }),
      '+34669701069',
    );
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
