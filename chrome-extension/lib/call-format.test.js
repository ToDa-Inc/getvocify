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
  callReviewAnchor,
  planOutboundCallUi,
  postCallCard,
  postCallNotice,
  shouldShowContactCallCta,
  snapshotCallOutcome,
  lastCallAsOutbound,
  applyCallPoll,
  isCallPollTerminal,
  dispositionMessage,
  isCarrierHangupError,
  isVoiceSdkGeneralError,
  isVoiceAccessTokenError,
  isExtensionRuntimeError,
  userFacingCallError,
  userFacingCallSetupError,
  connectWithVoiceTokenRecovery,
  applyVoiceTokenRefresh,
  CALL_ERROR_TOKEN_STALE,
  CALL_ERROR_EXTENSION_RESTARTED,
  CALL_ERROR_SESSION,
  CALL_ERROR_TOKEN_FETCH,
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

function tokenExpired() {
  return Object.assign(new Error('AccessTokenExpired'), { code: 20104 });
}

describe('connectWithVoiceTokenRecovery', () => {
  it('retries 20104 with a freshly minted JWT and a new Device', async () => {
    const attempts = [];
    const call = await connectWithVoiceTokenRecovery({
      token: 'stale',
      connect: async (token, forceNew) => {
        attempts.push({ token, forceNew });
        if (attempts.length === 1) throw tokenExpired();
        return { sid: 'CA1' };
      },
      remint: async () => 'fresh',
    });
    assert.equal(call.sid, 'CA1');
    assert.deepEqual(attempts, [
      { token: 'stale', forceNew: false },
      { token: 'fresh', forceNew: true },
    ]);
  });

  it('does not remint a carrier hangup', async () => {
    let reminted = 0;
    await assert.rejects(
      connectWithVoiceTokenRecovery({
        token: 'ok',
        connect: async () => {
          throw Object.assign(new Error('hangup'), { code: 31005 });
        },
        remint: async () => {
          reminted += 1;
          return 'fresh';
        },
      }),
      /hangup/,
    );
    assert.equal(reminted, 0);
  });

  it('does not remint twice when the fresh JWT also expires', async () => {
    let reminted = 0;
    await assert.rejects(
      connectWithVoiceTokenRecovery({
        token: 'stale',
        connect: async () => {
          throw tokenExpired();
        },
        remint: async () => {
          reminted += 1;
          return 'still-stale';
        },
      }),
      /AccessTokenExpired/,
    );
    assert.equal(reminted, 1);
  });
});

describe('applyVoiceTokenRefresh', () => {
  it('pushes a new JWT onto the live Device', async () => {
    const applied = [];
    let destroyed = false;
    await applyVoiceTokenRefresh({
      remint: async () => 'fresh',
      apply: (token) => applied.push(token),
      onFailure: () => {
        destroyed = true;
      },
    });
    assert.deepEqual(applied, ['fresh']);
    assert.equal(destroyed, false);
  });

  it('destroys the Device when minting fails so the next click starts clean', async () => {
    const applied = [];
    let destroyed = false;
    await applyVoiceTokenRefresh({
      remint: async () => {
        throw new Error('session expired');
      },
      apply: (token) => applied.push(token),
      onFailure: () => {
        destroyed = true;
      },
    });
    assert.deepEqual(applied, []);
    assert.equal(destroyed, true);
  });
});

describe('userFacingCallError', () => {
  it('rewrites Twilio AccessTokenExpired instead of showing the SDK string', () => {
    assert.equal(isVoiceAccessTokenError({ code: 20104, message: 'AccessTokenExpired' }), true);
    assert.equal(
      userFacingCallError({ code: 20104, message: 'AccessTokenExpired' }),
      CALL_ERROR_TOKEN_STALE,
    );
    assert.equal(
      userFacingCallError('31205 JWTTokenExpired: Access Token expired'),
      CALL_ERROR_TOKEN_STALE,
    );
  });

  it('rewrites a dead Chrome service worker as retry, not a Twilio outage', () => {
    assert.equal(
      isExtensionRuntimeError('Could not establish connection. Receiving end does not exist.'),
      true,
    );
    assert.equal(
      userFacingCallError('worker service not working'),
      CALL_ERROR_EXTENSION_RESTARTED,
    );
  });

  it('tells the user to reload when the Vocify session JWT is dead', () => {
    assert.equal(userFacingCallError({ status: 401, message: 'Session expired' }), CALL_ERROR_SESSION);
    assert.equal(userFacingCallSetupError({ status: 401 }), CALL_ERROR_SESSION);
    assert.equal(userFacingCallSetupError(new Error('network')), CALL_ERROR_TOKEN_FETCH);
  });

  it('keeps 31005 / 31000 silent so DialCallStatus can own the copy', () => {
    assert.equal(userFacingCallError({ code: 31005 }), null);
    assert.equal(userFacingCallError({ code: 31000, message: 'General Error' }), null);
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

  it('hides raw 31000 until DialCallStatus lands', () => {
    assert.deepEqual(
      postCallNotice({
        outcome: 'no_answer',
        errorMessage: 'UnknownError (31000): General Error',
      }),
      { visible: false, text: '' }
    );
  });

  it('maps 31000 through DialCallStatus, including failed', () => {
    assert.deepEqual(
      postCallNotice({
        outcome: 'no_answer',
        disposition: 'no_answer',
        errorMessage: 'UnknownError (31000): General Error',
      }),
      { visible: true, text: 'Sin respuesta' }
    );
    assert.deepEqual(
      postCallNotice({
        outcome: 'no_answer',
        disposition: 'failed',
        errorMessage: 'UnknownError (31000): General Error',
      }),
      { visible: true, text: 'Llamada fallida' }
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
    assert.equal(isCarrierHangupError('UnknownError (31000): General Error'), false);
  });
});

describe('isVoiceSdkGeneralError', () => {
  it('matches Voice JS SDK UnknownError 31000', () => {
    assert.equal(isVoiceSdkGeneralError('UnknownError (31000): General Error'), true);
    assert.equal(isVoiceSdkGeneralError({ code: 31000 }), true);
    assert.equal(isVoiceSdkGeneralError('31005 ConnectionError: Error sent from Gateway in HANGUP'), false);
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

describe('planOutboundCallUi', () => {
  const called = {
    outcome: 'answered',
    contactId: 'C-called',
    contactName: 'Ana',
    dealId: null,
    processing: true,
  };

  it('opens loading on the contact that was called, not the tab open now', () => {
    const plan = planOutboundCallUi({ lastCall: called, uiStatus: 'idle' });
    assert.equal(plan.type, 'processing');
    assert.equal(plan.anchor.objectType, 'contact');
    assert.equal(plan.anchor.recordId, 'C-called');
    assert.equal(plan.anchor.contactName, 'Ana');
  });

  it('opens review for that same contact when the memo is ready', () => {
    const plan = planOutboundCallUi({
      lastCall: { ...called, processing: false, memoId: 'm1', memoStatus: 'pending_review' },
      uiStatus: 'processing',
    });
    assert.equal(plan.type, 'review');
    assert.equal(plan.memoId, 'm1');
    assert.equal(plan.anchor.recordId, 'C-called');
  });

  it('does not reopen after the user left, and ignores a call that was not answered', () => {
    assert.equal(
      planOutboundCallUi({
        lastCall: { ...called, memoId: 'm1', memoStatus: 'pending_review', processing: false },
        uiStatus: 'idle',
        dismissed: true,
      }).type,
      'stay',
    );
    assert.equal(
      planOutboundCallUi({ lastCall: { outcome: 'no_answer', processing: false }, uiStatus: 'idle' }).type,
      'stay',
    );
  });

  it('anchors a deal call on that deal', () => {
    const anchor = callReviewAnchor({ dealId: 'D1', contactId: 'C1', dealName: 'Acme', provider: 'hubspot' });
    assert.equal(anchor.objectType, 'deal');
    assert.equal(anchor.recordId, 'D1');
    assert.equal(anchor.contactId, 'C1');
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

  it('replaces SDK 31000 with DialCallStatus, including failed', () => {
    const missed = applyCallPoll(
      {
        callSid: 'CA1',
        outcome: 'no_answer',
        errorMessage: 'UnknownError (31000): General Error',
        processing: false,
      },
      { callDisposition: 'no_answer', status: 'logged', errorMessage: null },
    );
    assert.equal(missed.disposition, 'no_answer');
    assert.equal(missed.errorMessage, null);
    const failed = applyCallPoll(
      {
        callSid: 'CA2',
        outcome: 'no_answer',
        errorMessage: 'UnknownError (31000): General Error',
        processing: false,
      },
      { callDisposition: 'failed', status: 'logged', errorMessage: null },
    );
    assert.equal(failed.disposition, 'failed');
    assert.equal(failed.errorMessage, null);
    assert.deepEqual(postCallNotice(failed), { visible: true, text: 'Llamada fallida' });
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
