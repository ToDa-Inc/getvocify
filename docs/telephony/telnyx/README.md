# Telnyx reference

Evaluated 2026-08-27 as a possible replacement for Twilio. **Outcome: not adopted.** Reasoning
in [../DECISION.md](../DECISION.md).

Kept as reference because the evaluation surfaced several designs that are better than what we
shipped, and because the decision should be revisited if the Short Duration surcharge changes
or Managed Accounts come downmarket.

| Document | What it covers | Headline finding |
|---|---|---|
| [caller-id-and-spain.md](caller-id-and-spain.md) | Verified Numbers API, country coverage, Spain regulatory, sub-user semantics, AUP risk | Telnyx documents **no** country restriction on verification, but also never documents Spain support. Its own Spain page states the same TDF/149/2025 mobile-CLI prohibition Twilio's does |
| [webrtc-and-mv3.md](webrtc-and-mv3.md) | `@telnyx/webrtc` package shape, MV3/CSP viability, auth model, server-authoritative caller ID | Both feasibility gates pass. Real UMD bundle (273,634 B, `globalThis.TelnyxWebRTC`), verified by executing it in a bare VM. "Park Outbound Calls" gives server-side caller-ID authority. No MV3 precedent exists anywhere |
| [recording-and-webhooks.md](recording-and-webhooks.md) | Dual-channel recording, delivery, download auth, Ed25519 webhook signatures, Call Control vs TeXML | Dual-channel WAV explicitly supported. Recording can be written **straight into our own bucket**. Signature covers `timestamp\|body` only — the URL is not signed |
| [pricing-and-multitenancy.md](pricing-and-multitenancy.md) | Spain rates, billing increments, Managed Accounts, usage attribution | Spain rates are published, and there is an **unauthenticated pricing API**. But 60/60 round-up, a $0.01/call surcharge on sub-6-second calls, and Managed Accounts gated at Enterprise |

## The three things worth stealing

1. **Direct-to-bucket recording delivery** (`POST /v2/custom_storage_credentials/{app_id}`).
   Removes our download hop, the pre-signed-URL race, and one credential we hold. Strictly
   better than what we built.
2. **Ed25519 webhook signatures over `timestamp|body`.** Because the request URL is not signed,
   the entire class of proxy/base-URL bugs we work around on Twilio cannot occur.
3. **The unauthenticated pricing API.**
   `GET api.telnyx.com/v2/pricing/products/elastic-sip-outbound?filter[country_iso]=ES`
   returns the real rate deck with no login. Useful for cost modelling whichever carrier we
   use.

## The one thing that disqualifies it today

The Short Duration surcharge: once >15% of a month's calls are ≤6 s, Telnyx applies $0.01 per
call **retroactively to all of them**, and states "We do not support use cases that require
Short Duration calls." SDR cold-dialling is predominantly sub-6-second calls. This is aimed
at our exact usage pattern.

## Open questions for Telnyx sales

Ordered by how much they would change the decision.

1. Does the Short Duration surcharge apply to outbound SDR dialling where short calls are
   unanswered rings and voicemail drops rather than intentional short-duration traffic?
2. Which origination band does a `+34` caller ID fall into — `"local"` or "From EEA"? Worth
   33× on the landline rate, and not published.
3. Are Managed Accounts available below Enterprise for an ISV, and what is the actual
   qualification bar?
4. Is the 10,000-minute recording-storage tier monthly or cumulative?
5. Can Verified Numbers be used with Spanish `+34` numbers at all, and is the scope per
   Managed Account?
6. Does a bridged two-leg call bill recording once or twice?
7. What is the concurrency ceiling above the documented 10 calls/hour on Paid, and what lifts
   it?
