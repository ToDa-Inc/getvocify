import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { CALL_STATES } from './dialer.js';
import {
  contactCallCta,
  contactCallHint,
  contactCallTooltip,
  describeCallState,
  dialerPanelMode,
  formatCallDuration,
  memoBusyLabel,
  outboundActivityChrome,
  postCallCard,
  postCallNotice,
  shouldShowContactCallCta,
  snapshotCallOutcome,
  lastCallAsOutbound,
  applyCallPoll,
  isCallPollTerminal,
  dispositionMessage,
  isCarrierHangupError,
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
      { visible: false, phone: null, label: '', caption: '', ready: false }
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
        ready: true,
      }
    );
  });

  it('falls back to a generic label without a name', () => {
    assert.equal(
      contactCallCta({ contactPhone: '+34600111222', contactName: '' }).label,
      'Llamar a este contacto'
    );
  });

  it('still shows Call when the contact has a phone but caller ID is not ready', () => {
    const cta = contactCallCta({
      contactPhone: '+34648739267',
      contactName: 'Toni Mora',
      canPlaceCall: false,
    });
    assert.equal(cta.visible, true);
    assert.equal(cta.ready, false);
    assert.equal(cta.label, 'Llamar a Toni');
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

  it('asks to set up calling when the contact has a phone but calling is off', () => {
    assert.equal(
      dialerPanelMode({
        contactPhone: '+34648739267',
        callingEnabled: false,
        callState: CALL_STATES.IDLE,
      }),
      'setup'
    );
  });
});

describe('shouldShowContactCallCta', () => {
  const cta = { visible: true };

  it('shows the Call row for a ready contact, missing caller ID, or unset calling', () => {
    assert.equal(shouldShowContactCallCta('contact', cta), true);
    assert.equal(shouldShowContactCallCta('needs-cli', cta), true);
    assert.equal(shouldShowContactCallCta('setup', cta), true);
  });

  it('does not show Call while live or when the CTA is hidden', () => {
    assert.equal(shouldShowContactCallCta('live', cta), false);
    assert.equal(shouldShowContactCallCta('contact', { visible: false }), false);
    assert.equal(shouldShowContactCallCta('hidden', cta), false);
  });
});

describe('contactCallHint', () => {
  it('points missing caller ID and unset calling at Calling settings', () => {
    assert.deepEqual(
      contactCallHint({ mode: 'needs-cli', objectType: 'contact', hasPhone: true }),
      {
        text: 'Add your number in Calling settings to place this call',
        action: 'calling-settings',
      }
    );
    assert.deepEqual(
      contactCallHint({ mode: 'setup', objectType: 'contact', hasPhone: true }),
      {
        text: "Calling isn't set up for this account. Open Calling settings.",
        action: 'calling-settings',
      }
    );
  });

  it('does not send a no-phone HubSpot contact to Vocify calling settings', () => {
    assert.deepEqual(
      contactCallHint({ mode: 'hidden', objectType: 'contact', hasPhone: false }),
      { text: 'No phone number on this contact', action: null }
    );
  });

  it('stays quiet on inbox or when Call is ready', () => {
    assert.deepEqual(contactCallHint({ mode: 'contact', objectType: 'contact', hasPhone: true }), {
      text: '',
      action: null,
    });
    assert.deepEqual(contactCallHint({ mode: 'hidden', objectType: null, hasPhone: false }), {
      text: '',
      action: null,
    });
  });
});

describe('contactCallTooltip', () => {
  it('puts the setup copy on Call when the account is not ready', () => {
    const hint = contactCallHint({ mode: 'needs-cli', hasPhone: true });
    assert.equal(
      contactCallTooltip({ ready: false, caption: '+34 600 11 12 22', hint }),
      hint.text
    );
  });

  it('keeps the phone caption when Call can dial', () => {
    assert.equal(
      contactCallTooltip({
        ready: true,
        caption: '+34 600 11 12 22',
        hint: contactCallHint({ mode: 'contact', hasPhone: true }),
      }),
      '+34 600 11 12 22'
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

  it('does not treat a Twilio 31005 hangup as a server miss', () => {
    assert.deepEqual(
      postCallNotice({
        outcome: 'no_answer',
        errorMessage: '31005 ConnectionError: Error sent from Gateway in HANGUP',
      }),
      { visible: true, text: 'Sin respuesta' }
    );
  });

  it('shows busy when DialCallStatus says so, even if the SDK sent 31005', () => {
    assert.deepEqual(
      postCallNotice({
        outcome: 'no_answer',
        disposition: 'busy',
        errorMessage: '31005 ConnectionError: Error sent from Gateway in HANGUP',
      }),
      { visible: true, text: 'Ocupado' }
    );
  });

  it('keeps the TwiML application-error copy when the Voice URL never succeeded', () => {
    assert.deepEqual(
      postCallNotice({
        outcome: 'no_answer',
        errorMessage: 'Application error',
      }),
      {
        visible: true,
        text: 'Twilio no alcanzó el servidor',
      }
    );
  });
});

describe('isCarrierHangupError', () => {
  it('matches Twilio 31005 hangup noise, not a TwiML application error', () => {
    assert.equal(isCarrierHangupError('31005 ConnectionError: Error sent from Gateway in HANGUP'), true);
    assert.equal(isCarrierHangupError({ code: 31005, message: 'Connection error' }), true);
    assert.equal(isCarrierHangupError('Application error'), false);
  });
});

describe('dispositionMessage', () => {
  it('uses the same busy / no-answer copy as the dashboard dialer', () => {
    assert.equal(dispositionMessage('busy'), 'Ocupado');
    assert.equal(dispositionMessage('no_answer'), 'Sin respuesta');
    assert.equal(dispositionMessage('canceled'), 'Llamada cancelada');
    assert.equal(dispositionMessage('failed'), 'Llamada fallida');
    assert.equal(dispositionMessage('connected'), null);
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

  it('does not treat a 31005 hangup on an answered call as a failed card', () => {
    assert.equal(
      postCallCard({
        processing: false,
        errorMessage: '31005 ConnectionError: Error sent from Gateway in HANGUP',
        durationLabel: '0:06',
      }).kind,
      'busy',
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

  it('labels busy and no-answer instead of offering Reintentar', () => {
    assert.deepEqual(
      outboundActivityChrome({ status: 'busy', to: '+34600111222' }),
      { kind: 'status', label: 'Ocupado' },
    );
    assert.deepEqual(
      outboundActivityChrome({ status: 'no_answer', to: '+34600111222' }),
      { kind: 'status', label: 'Sin respuesta' },
    );
    assert.deepEqual(
      outboundActivityChrome({ status: 'logged', callDisposition: 'busy', to: '+34600111222' }),
      { kind: 'status', label: 'Ocupado' },
    );
  });

  it('still offers Reintentar when the carrier marked the call failed', () => {
    assert.deepEqual(
      outboundActivityChrome({ status: 'failed', to: '+34600111222', from: '+34910000000' }),
      { kind: 'redial', label: 'Reintentar', to: '+34600111222', from: '+34910000000' },
    );
  });

  it('does not offer Reintentar on a logged call with no carrier failure', () => {
    assert.deepEqual(
      outboundActivityChrome({ status: 'logged', to: '+34600111222', from: '+34910000000' }),
      { kind: 'none', label: '' },
    );
  });
});

describe('snapshotCallOutcome', () => {
  it('treats an in-progress connected call as answered even if accept missed answeredAt', () => {
    assert.equal(
      snapshotCallOutcome({ callState: CALL_STATES.ACTIVE, answeredAt: null }),
      'answered',
    );
  });

  it('keeps ringing hangups as no_answer', () => {
    assert.equal(
      snapshotCallOutcome({ callState: CALL_STATES.RINGING, answeredAt: null }),
      'no_answer',
    );
  });
});

describe('lastCallAsOutbound', () => {
  it('does not mark a ringing hangup as Processing', () => {
    const row = lastCallAsOutbound({
      callSid: 'CA1',
      to: '+34600111222',
      outcome: 'no_answer',
      processing: false,
      endedAt: Date.now(),
    });
    assert.deepEqual(outboundActivityChrome(row), { kind: 'status', label: 'Sin respuesta' });
  });

  it('carries busy disposition onto the activity row', () => {
    const row = lastCallAsOutbound({
      callSid: 'CA1',
      to: '+34600111222',
      outcome: 'no_answer',
      disposition: 'busy',
      processing: false,
      endedAt: Date.now(),
    });
    assert.equal(row.status, 'busy');
    assert.deepEqual(outboundActivityChrome(row), { kind: 'status', label: 'Ocupado' });
  });

  it('offers Reintentar only when TwiML never ran', () => {
    const row = lastCallAsOutbound({
      callSid: 'CA1',
      to: '+34600111222',
      callerId: '+34910000000',
      outcome: 'no_answer',
      processing: false,
      errorMessage: 'Application error',
      endedAt: Date.now(),
    });
    assert.equal(row.status, 'failed');
    assert.deepEqual(outboundActivityChrome(row), {
      kind: 'redial',
      label: 'Reintentar',
      to: '+34600111222',
      from: '+34910000000',
    });
  });

  it('shows Processing while an answered call is still uploading', () => {
    const row = lastCallAsOutbound({
      callSid: 'CA1',
      outcome: 'answered',
      processing: true,
      answeredAt: Date.now(),
    });
    assert.equal(outboundActivityChrome(row).kind, 'busy');
    assert.equal(outboundActivityChrome(row).label, 'Processing');
  });
});

describe('applyCallPoll', () => {
  it('replaces SDK 31005 with DialCallStatus from GET /calls', () => {
    const next = applyCallPoll(
      {
        callSid: 'CA1',
        outcome: 'no_answer',
        errorMessage: '31005 ConnectionError: Error sent from Gateway in HANGUP',
        processing: false,
      },
      { callDisposition: 'busy', status: 'logged', errorMessage: null },
    );
    assert.equal(next.disposition, 'busy');
    assert.equal(next.errorMessage, null);
    assert.equal(next.processing, false);
  });

  it('keeps polling when HubSpot logs the call before extraction finishes', () => {
    const next = applyCallPoll(
      { callSid: 'CA399', outcome: 'answered', processing: true },
      {
        status: 'logged',
        memoId: 'ff4731b4',
        memoStatus: 'extracting',
        callDisposition: 'connected',
      },
    );
    assert.equal(next.processing, true);
    assert.equal(
      isCallPollTerminal({
        status: 'logged',
        memoId: 'ff4731b4',
        memoStatus: 'extracting',
        callDisposition: 'connected',
      }),
      false,
    );
    assert.equal(
      isCallPollTerminal({
        status: 'logged',
        memoId: 'ff4731b4',
        memoStatus: 'pending_transcript',
        callDisposition: 'connected',
      }),
      false,
    );
    assert.equal(
      isCallPollTerminal({
        status: 'logged',
        memoId: 'ff4731b4',
        memoStatus: 'pending_review',
        callDisposition: 'connected',
      }),
      true,
    );
  });

  it('stops a logged call with no memo, and a missed disposition', () => {
    assert.equal(
      isCallPollTerminal({ status: 'logged', memoId: null, memoStatus: null }),
      true,
    );
    assert.equal(
      isCallPollTerminal({
        status: 'logged',
        memoId: 'm1',
        memoStatus: 'extracting',
        callDisposition: 'busy',
      }),
      false,
    );
    assert.equal(
      isCallPollTerminal({
        status: 'logged',
        memoId: null,
        memoStatus: null,
        callDisposition: 'no_answer',
      }),
      true,
    );
  });

  it('keeps polling pending_review only while auto-sync may still write', () => {
    const reviewing = {
      status: 'logged',
      memoId: 'm1',
      memoStatus: 'pending_review',
      callDisposition: 'connected',
    };
    assert.equal(isCallPollTerminal(reviewing, { autoSync: true }), false);
    assert.equal(
      isCallPollTerminal(
        { ...reviewing, screeningOutcome: 'voicemail' },
        { autoSync: true },
      ),
      true,
    );
    assert.equal(
      isCallPollTerminal({ ...reviewing, memoStatus: 'approved' }, { autoSync: true }),
      true,
    );
  });
});
