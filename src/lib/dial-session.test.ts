import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { CALL_STATES } from "./dial-target.ts";
import { productCatalog } from "./product-catalog.ts";
import {
  fetchVoiceTokenAfterRingback,
  mapTelnyxCallState,
  ringbackTimedOut,
  startLocalRingback,
  TELNYX_RINGBACK_SRC,
  TELNYX_RING_TIMEOUT_MS,
  telnyxHangupMessage,
  telnyxNewCallOptions,
  telnyxRtcClientOptions,
  vocifyCallHeaders,
  voiceClientFromToken,
  dispositionMessage,
  isCarrierHangupError,
  isVoiceSdkGeneralError,
  isVoiceAccessTokenError,
  userFacingCallError,
  callErrorStart,
} from "./dial-session.ts";

const callCopy = productCatalog.ES;

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
    assert.equal(dispositionMessage("busy", callCopy), callCopy.callBusy);
    assert.equal(dispositionMessage("no_answer", callCopy), callCopy.callNoAnswer);
    assert.equal(dispositionMessage("canceled", callCopy), callCopy.callCanceled);
    assert.equal(dispositionMessage("failed", callCopy), callCopy.callFailed);
    assert.equal(dispositionMessage("connected", callCopy), null);
  });
});

describe("callErrorStart", () => {
  it("returns the catalog start-call message", () => {
    assert.equal(callErrorStart(callCopy), callCopy.callStartFailed);
    assert.equal(callErrorStart(productCatalog.EN), productCatalog.EN.callStartFailed);
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

  it("does not treat 31000 as 31005 — geo-permission failures also arrive as 31000", () => {
    assert.equal(isCarrierHangupError("UnknownError (31000): General Error"), false);
    assert.equal(isCarrierHangupError({ code: 31000 }), false);
  });
});

describe("userFacingCallError", () => {
  it("rewrites Twilio AccessTokenExpired instead of showing the SDK string", () => {
    assert.equal(isVoiceAccessTokenError({ code: 20104, message: "AccessTokenExpired" }), true);
    assert.equal(
      userFacingCallError({ code: 20104, message: "AccessTokenExpired" }, callCopy),
      callCopy.callTokenStale,
    );
    assert.equal(
      userFacingCallError("worker service not working", callCopy),
      callCopy.callExtensionRestarted,
    );
  });
});

describe("isVoiceSdkGeneralError", () => {
  it("matches Voice JS SDK UnknownError 31000", () => {
    assert.equal(isVoiceSdkGeneralError("UnknownError (31000): General Error"), true);
    assert.equal(isVoiceSdkGeneralError({ code: 31000, message: "General Error" }), true);
  });

  it("does not match a TwiML miss or 31005 hangup wrap", () => {
    assert.equal(isVoiceSdkGeneralError("Application error"), false);
    assert.equal(
      isVoiceSdkGeneralError("31005 ConnectionError: Error sent from Gateway in HANGUP"),
      false,
    );
  });
});

describe("telnyxHangupMessage", () => {
  it("maps SIP 486 / Q.850 17 to Ocupado", () => {
    assert.equal(telnyxHangupMessage({ sipCode: 486 }, callCopy), callCopy.callBusy);
    assert.equal(telnyxHangupMessage({ causeCode: 17 }, callCopy), callCopy.callBusy);
    assert.equal(telnyxHangupMessage({ cause: "USER_BUSY" }, callCopy), callCopy.callBusy);
    assert.equal(telnyxHangupMessage({ hangupCause: "USER_BUSY" }, callCopy), callCopy.callBusy);
  });

  it("returns null for a normal hangup", () => {
    assert.equal(telnyxHangupMessage({ sipCode: 200, causeCode: 16 }, callCopy), null);
    assert.equal(telnyxHangupMessage(null, callCopy), null);
  });
});

describe("fetchVoiceTokenAfterRingback", () => {
  it("starts the tone before the token request settles", async () => {
    const order: string[] = [];
    let release!: (value: string) => void;
    const pending = new Promise<string>((resolve) => {
      release = resolve;
    });
    const done = fetchVoiceTokenAfterRingback(
      () => {
        order.push("ring");
        return () => {
          order.push("stop");
        };
      },
      () => {
        order.push("token");
        return pending;
      },
    );
    assert.deepEqual(order, ["ring", "token"]);
    release("jwt");
    const { token } = await done;
    assert.equal(token, "jwt");
  });

  it("stops the tone if the token fetch fails", async () => {
    const order: string[] = [];
    await assert.rejects(
      fetchVoiceTokenAfterRingback(
        () => {
          order.push("ring");
          return () => {
            order.push("stop");
          };
        },
        async () => {
          throw new Error("no token");
        },
      ),
      /no token/,
    );
    assert.deepEqual(order, ["ring", "stop"]);
  });
});

describe("startLocalRingback", () => {
  it("calls play in the same turn", () => {
    let played = false;
    const fake = {
      loop: false,
      play() {
        played = true;
        return Promise.resolve();
      },
      pause() {},
      removeAttribute() {},
      load() {},
    };
    const stop = startLocalRingback("/x.wav", 35_000, () => fake as HTMLAudioElement);
    assert.equal(played, true);
    stop();
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
