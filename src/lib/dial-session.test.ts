import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { CALL_STATES } from "./dial-target.ts";
import {
  mapTelnyxCallState,
  ringbackTimedOut,
  TELNYX_RINGBACK_SRC,
  TELNYX_RING_TIMEOUT_MS,
  telnyxHangupMessage,
  telnyxNewCallOptions,
  telnyxRtcClientOptions,
  vocifyCallHeaders,
  voiceClientFromToken,
  dispositionMessage,
  isCarrierHangupError,
} from "./dial-session.ts";

describe("voiceClientFromToken", () => {
  it("uses Telnyx when the token says telnyx", () => {
    assert.equal(voiceClientFromToken("telnyx"), "telnyx");
  });

  it("keeps Twilio for twilio, missing, or unknown providers", () => {
    assert.equal(voiceClientFromToken("twilio"), "twilio");
    assert.equal(voiceClientFromToken(undefined), "twilio");
    assert.equal(voiceClientFromToken("vonage"), "twilio");
  });
});

describe("vocifyCallHeaders", () => {
  it("emits caller, contact, and deal headers in that order", () => {
    assert.deepEqual(
      vocifyCallHeaders({
        callerId: "+34600111222",
        contactId: "c1",
        dealId: "d1",
      }),
      [
        { name: "X-Vocify-Caller-Id", value: "+34600111222" },
        { name: "X-Vocify-Contact-Id", value: "c1" },
        { name: "X-Vocify-Deal-Id", value: "d1" },
      ],
    );
  });

  it("omits blank fields and stringifies numeric ids", () => {
    assert.deepEqual(
      vocifyCallHeaders({ callerId: "", contactId: 42, dealId: null }),
      [{ name: "X-Vocify-Contact-Id", value: "42" }],
    );
  });
});

describe("telnyxRtcClientOptions", () => {
  it("passes the JWT and local ringback file", () => {
    assert.deepEqual(telnyxRtcClientOptions("jwt-1"), {
      login_token: "jwt-1",
      ringbackFile: TELNYX_RINGBACK_SRC,
    });
  });
});

describe("telnyxNewCallOptions", () => {
  it("builds a parked WebRTC dial with Vocify SIP headers", () => {
    assert.deepEqual(
      telnyxNewCallOptions({
        to: "+34600999888",
        callerId: "+34669701069",
        contactId: "hs-1",
      }),
      {
        destinationNumber: "+34600999888",
        audio: true,
        customHeaders: [
          { name: "X-Vocify-Caller-Id", value: "+34669701069" },
          { name: "X-Vocify-Contact-Id", value: "hs-1" },
        ],
      },
    );
  });
});

describe("dispositionMessage", () => {
  it("maps carrier dispositions to the dialer toast copy", () => {
    assert.equal(dispositionMessage("busy"), "Ocupado");
    assert.equal(dispositionMessage("no_answer"), "Sin respuesta");
    assert.equal(dispositionMessage("canceled"), "Llamada cancelada");
    assert.equal(dispositionMessage("failed"), "Llamada fallida");
    assert.equal(dispositionMessage("connected"), null);
  });
});

describe("isCarrierHangupError", () => {
  it("matches Twilio 31005 hangup noise", () => {
    assert.equal(
      isCarrierHangupError("31005 ConnectionError: Error sent from Gateway in HANGUP"),
      true,
    );
    assert.equal(isCarrierHangupError({ code: 31005 }), true);
    assert.equal(isCarrierHangupError("Application error"), false);
  });
});

describe("telnyxHangupMessage", () => {
  it("maps SIP 486 / Q.850 17 to Ocupado", () => {
    assert.equal(telnyxHangupMessage({ sipCode: 486 }), "Ocupado");
    assert.equal(telnyxHangupMessage({ causeCode: 17 }), "Ocupado");
    assert.equal(telnyxHangupMessage({ cause: "USER_BUSY" }), "Ocupado");
    assert.equal(telnyxHangupMessage({ hangupCause: "USER_BUSY" }), "Ocupado");
  });

  it("returns null for a normal hangup", () => {
    assert.equal(telnyxHangupMessage({ sipCode: 200, causeCode: 16 }), null);
    assert.equal(telnyxHangupMessage(null), null);
  });
});

describe("ringbackTimedOut", () => {
  it("caps Telnyx ringback at the PSTN timeout, not forever", () => {
    assert.equal(TELNYX_RING_TIMEOUT_MS, 35_000);
    assert.equal(ringbackTimedOut(0, 34_999), false);
    assert.equal(ringbackTimedOut(0, 35_000), true);
  });
});

describe("mapTelnyxCallState", () => {
  it("maps Telnyx client states onto the dashboard call machine", () => {
    assert.equal(mapTelnyxCallState("trying"), CALL_STATES.RINGING);
    assert.equal(mapTelnyxCallState("ringing"), CALL_STATES.RINGING);
    assert.equal(mapTelnyxCallState("early"), CALL_STATES.RINGING);
    assert.equal(mapTelnyxCallState("active"), CALL_STATES.ACTIVE);
    assert.equal(mapTelnyxCallState("held"), CALL_STATES.ACTIVE);
    assert.equal(mapTelnyxCallState("hangup"), CALL_STATES.IDLE);
    assert.equal(mapTelnyxCallState("destroy"), CALL_STATES.IDLE);
  });
});
