import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { CALL_STATES } from './dialer.js';
import {
  contactCallCta,
  describeCallState,
  dialerPanelMode,
  formatCallDuration,
  memoBusyLabel,
  outboundActivityChrome,
  postCallCard,
  postCallNotice,
} from './call-format.js';

describe('formatCallDuration', () => {
  it('formats seconds as m:ss', () => {
    assert.equal(formatCallDuration(0), '0:00');
    assert.equal(formatCallDuration(7000), '0:07');
    assert.equal(formatCallDuration(59000), '0:59');
    assert.equal(formatCallDuration(60000), '1:00');
    assert.equal(formatCallDuration(723000), '12:03');
  });

  it('formats hours', () => {
    assert.equal(formatCallDuration(3661000), '1:01:01');
  });

  it('treats negative and non-finite as 0:00', () => {
    assert.equal(formatCallDuration(-1), '0:00');
    assert.equal(formatCallDuration(NaN), '0:00');
    assert.equal(formatCallDuration(Infinity), '0:00');
    assert.equal(formatCallDuration(undefined), '0:00');
  });
});

describe('describeCallState', () => {
  it('labels connecting, ringing, ending', () => {
    assert.equal(describeCallState({ state: CALL_STATES.CONNECTING }), 'Conectando…');
    assert.equal(
      describeCallState({ state: CALL_STATES.RINGING, to: '+34600111222' }),
      'Llamando a +34600111222…'
    );
    assert.equal(describeCallState({ state: CALL_STATES.ENDING }), 'Colgando…');
  });

  it('keeps duration and mute off the status — the timer and mic own those', () => {
    assert.equal(
      describeCallState({
        state: CALL_STATES.ACTIVE,
        answeredAt: 3000,
        now: 10_000,
        muted: false,
      }),
      'En llamada'
    );
    assert.equal(
      describeCallState({
        state: CALL_STATES.ACTIVE,
        answeredAt: 3000,
        now: 10_000,
        muted: true,
      }),
      'En llamada'
    );
  });
});

describe('contactCallCta', () => {
  it('is hidden when there is no contact phone', () => {
    assert.deepEqual(
      contactCallCta({ contactPhone: null, contactName: 'Toni Mora' }),
      { visible: false, phone: null, label: '', caption: '' }
    );
  });

  it('is hidden while a call is already in progress', () => {
    assert.equal(
      contactCallCta({
        contactPhone: '+34648739267',
        contactName: 'Toni Mora',
        callState: CALL_STATES.ACTIVE,
      }).visible,
      false
    );
  });

  it('labels with the given name when the record has a phone', () => {
    assert.deepEqual(
      contactCallCta({
        contactPhone: '+34648739267',
        contactName: 'Toni Mora',
        callState: CALL_STATES.IDLE,
      }),
      {
        visible: true,
        phone: '+34648739267',
        label: 'Llamar a Toni',
        caption: '+34 648 73 92 67',
      }
    );
  });

  it('falls back to a generic label without a name', () => {
    assert.equal(
      contactCallCta({ contactPhone: '+34600111222', contactName: '' }).label,
      'Llamar a este contacto'
    );
  });

  it('is hidden when there is no verified caller ID', () => {
    assert.equal(
      contactCallCta({
        contactPhone: '+34648739267',
        contactName: 'Toni Mora',
        canPlaceCall: false,
      }).visible,
      false
    );
  });

  it('leaves non-Spanish numbers unformatted in the caption', () => {
    assert.equal(
      contactCallCta({ contactPhone: '+14155552671' }).caption,
      '+14155552671'
    );
  });
});

describe('dialerPanelMode', () => {
  it('hides the panel when idle and not on a contact', () => {
    assert.equal(
      dialerPanelMode({ contactPhone: null, callState: CALL_STATES.IDLE }),
      'hidden'
    );
  });

  it('shows a contact CTA when the record has a phone', () => {
    assert.equal(
      dialerPanelMode({
        contactPhone: '+34648739267',
        canPlaceCall: true,
        callState: CALL_STATES.IDLE,
      }),
      'contact'
    );
  });

  it('keeps live controls on screen during a call even off a contact', () => {
    assert.equal(
      dialerPanelMode({ contactPhone: null, callState: CALL_STATES.RINGING }),
      'live'
    );
  });

  it('shows post-call follow-up only after an answered call', () => {
    assert.equal(
      dialerPanelMode({
        contactPhone: '+34648739267',
        lastCall: { to: '+34648739267', outcome: 'answered' },
        callState: CALL_STATES.IDLE,
      }),
      'postcall'
    );
  });

  it('keeps the contact CTA after a no-answer so retry is the same button', () => {
    assert.equal(
      dialerPanelMode({
        contactPhone: '+34648739267',
        lastCall: { to: '+34648739267', outcome: 'no_answer' },
        canPlaceCall: true,
        callState: CALL_STATES.IDLE,
      }),
      'contact'
    );
  });

  it('asks to verify when the contact has a phone but no caller ID', () => {
    assert.equal(
      dialerPanelMode({
        contactPhone: '+34648739267',
        canPlaceCall: false,
        callState: CALL_STATES.IDLE,
      }),
      'needs-cli'
    );
  });
});

describe('postCallNotice', () => {
  it('is hidden when there is no last call', () => {
    assert.deepEqual(postCallNotice(null), { visible: false, text: '' });
  });

  it('is hidden after an answered call — that uses the follow-up card', () => {
    assert.equal(
      postCallNotice({ outcome: 'answered', processing: true }).visible,
      false
    );
  });

  it('labels a clean miss as no answer', () => {
    assert.deepEqual(
      postCallNotice({ outcome: 'no_answer' }),
      { visible: true, text: 'Sin respuesta' }
    );
  });

  it('explains a Twilio webhook miss instead of calling it no answer', () => {
    assert.deepEqual(
      postCallNotice({
        outcome: 'no_answer',
        errorMessage: '31005 Connection declined',
      }),
      {
        visible: true,
        text: 'Twilio no alcanzó el servidor',
      }
    );
  });
});

describe('postCallCard', () => {
  it('asks to review only when auto-sync is off', () => {
    assert.deepEqual(
      postCallCard({
        memoStatus: 'pending_review',
        memoId: 'm1',
        durationLabel: '1:15',
        autoSync: false,
      }),
      {
        kind: 'review',
        text: 'Llamada de 1:15 · listo para revisar',
        actionLabel: 'Revisar',
        memoId: 'm1',
      },
    );
  });

  it('keeps writing copy while auto-sync may still approve', () => {
    assert.equal(
      postCallCard({
        memoStatus: 'pending_review',
        memoId: 'm1',
        durationLabel: '1:15',
        autoSync: true,
      }).kind,
      'busy',
    );
  });

  it('does not stay on writing when screening skipped the CRM write', () => {
    assert.deepEqual(
      postCallCard({
        memoStatus: 'pending_review',
        memoId: 'm1',
        durationLabel: '1:03',
        autoSync: true,
        screeningOutcome: 'voicemail',
      }),
      {
        kind: 'review',
        text: 'Llamada de 1:03 · marcada como buzón',
        actionLabel: 'Revisar',
        memoId: 'm1',
      },
    );
  });

  it('shows the call as already written after approve', () => {
    assert.deepEqual(
      postCallCard({
        memoStatus: 'approved',
        memoId: 'm1',
        durationLabel: '1:15',
      }),
      {
        kind: 'synced',
        text: 'Llamada de 1:15 · escrito en CRM',
        actionLabel: 'Ver',
        memoId: 'm1',
      },
    );
  });
});

describe('memoBusyLabel', () => {
  it('uses the same English labels as HubSpot activity rows', () => {
    assert.equal(memoBusyLabel('uploading'), 'Uploading');
    assert.equal(memoBusyLabel('transcribing'), 'Transcribing');
    assert.equal(memoBusyLabel('extracting'), 'Extracting');
    assert.equal(memoBusyLabel('pending_review'), null);
    assert.equal(memoBusyLabel('approved'), null);
  });
});

describe('outboundActivityChrome', () => {
  it('does not call every in-flight outbound call Transcribing', () => {
    assert.deepEqual(
      outboundActivityChrome({ memoId: 'm1', memoStatus: 'extracting' }),
      { kind: 'busy', label: 'Extracting' },
    );
    assert.deepEqual(
      outboundActivityChrome({ memoId: 'm1', memoStatus: 'transcribing' }),
      { kind: 'busy', label: 'Transcribing' },
    );
    assert.deepEqual(
      outboundActivityChrome({ memoId: 'm1', memoStatus: 'pending_review' }),
      { kind: 'continue', label: 'Continue', memoId: 'm1' },
    );
    assert.deepEqual(
      outboundActivityChrome({ memoId: 'm1', memoStatus: 'pending_review', autoSync: true }),
      { kind: 'busy', label: 'Writing' },
    );
    assert.deepEqual(
      outboundActivityChrome({
        memoId: 'm1',
        memoStatus: 'pending_review',
        autoSync: true,
        screeningOutcome: 'voicemail',
      }),
      { kind: 'continue', label: 'Continue', memoId: 'm1' },
    );
    assert.deepEqual(
      outboundActivityChrome({ memoId: 'm1', memoStatus: 'approved' }),
      { kind: 'view', label: 'View', memoId: 'm1' },
    );
  });

  it('does not treat dialing as transcription', () => {
    assert.deepEqual(
      outboundActivityChrome({ status: 'dialing', to: '+3466008692355' }),
      { kind: 'none', label: '' },
    );
  });

  it('uses Processing only when the call is recorded and memo status is still unknown', () => {
    assert.deepEqual(
      outboundActivityChrome({ status: 'recorded', memoId: 'm1' }),
      { kind: 'busy', label: 'Processing' },
    );
  });
});
