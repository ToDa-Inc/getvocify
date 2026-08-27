# Carrier decision: Twilio vs Telnyx for Vocify outbound calling

**Date:** 2026-08-27
**Question asked:** should we move outbound calling from Twilio to Telnyx?
**Answer:** no — and the question is not the one that matters.

## Verdict

**Stay on Twilio. And stop trying to be the carrier in Spain — capture the audio at the
endpoint instead.**

Two separate answers, because the investigation turned up two separate questions.

**On the carrier question: no, do not migrate.** The reason to consider Telnyx was that Spanish
caller ID was not working the way the design assumed. The cause is Spanish law, which binds
both carriers identically — Telnyx's own Spain page states the same prohibition Twilio's does.
Migrating would cost 2–4 engineer-weeks (see
[portability audit](portability/carrier-coupling-audit.md)) and leave us in exactly the same
legal position. Telnyx is genuinely better on cheaper minutes, a cleaner webhook signature
scheme, and recording delivered straight into our own bucket — and none of those is the axis
currently blocking us.

**On the caller-ID question: the whole approach is a dead end in Spain, with a hard deadline.**
From **2026-10-17**, [Resolución SETID de 14 de abril de 2026](https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8409)
provides that commercial calls may only originate from the new **400** range. A 400 number is
held by an operator, is assigned by the CNMC, and **cannot receive incoming calls at all**. It
can never be an SDR's own number. In Spain, "present your own caller ID" and "make a commercial
call" become mutually exclusive.

That is seven weeks away, and it is the third moving target in eighteen months in one
jurisdiction. HubSpot's country page documents CLI suppression or blocking in seven others.
Being a telco in 27 divergent regimes is not the business we are in.

### The strategic reframe

The original goal was never to be a carrier. It was to **own the conversation data** instead of
depending on Aircall's API. Those are separable, and we conflated them:

- Owning the audio and the intelligence layer — the actual moat.
- Being the entity that originates the call — a regulated, jurisdiction-specific,
  fast-moving liability that generates no defensibility.

**Endpoint capture gives us the first without the second.** We already have most of it: the
Companion desktop app captures mic plus system audio, and the extension's offscreen document
already does tab capture. If the SDR calls from whatever they already use — Aircall, Ringover,
a softphone, a desk phone, a mobile on speaker — Vocify captures the audio locally and owns it
outright.

That path has no caller-ID problem, no regulatory bundle, no 400 range, no per-country
telephony law, and no carrier dependency of any kind. It is strictly *more* control over the
data than any carrier API gives us, because it depends on no carrier. It also covers calls we
could never reach through an integration, including the field-sales case.

The dialer we built keeps its value, but as a convenience in markets where BYO-CLI works or
where a tenant DID is provisioned — not as the mechanism the data depends on.

### The options, ranked

| | Option | Legal exposure | Effort | Verdict |
|---|---|---|---|---|
| **A** | **Endpoint capture** — record locally regardless of how the call is placed | None from telephony law; consent-to-record is data protection, which we already handle | Low — Companion and offscreen capture already exist | **Recommended as the strategic core** |
| **B** | Tenant-provisioned `+34 9x` geographic DID | Clean today. Open question from 2026-10-17 | Medium — per-tenant KYC becomes an onboarding step | Tactical option for customers who want click-to-call now. This is what HubSpot does |
| **C** | BYO caller ID as shipped | Art. 9 exposure for mobiles; partial silent delivery failure. HubSpot documents it fails in Spain | Already built | **Do not keep as the Spanish default** |
| **D** | Port the SDR's landline to our carrier | Clean, and genuinely still "their number" | High, slow | Only for a customer who specifically asks |
| **E** | 400 range | The only explicitly sanctioned path from October | Requires a carrier holding CNMC 400 assignments — Twilio almost certainly will not by October | Watch, do not plan on it |

Row C is worth dwelling on, because it is the most useful finding here: HubSpot ships this
exact feature, on Twilio, and documents that in Spain *"you may receive an error message, and
the call will not be completed."* The market leader tried it and its answer in Spain is
carrier-owned geographic numbering. That settles the empirical question more cheaply than any
test we could run.

## Side-by-side, with sources

Every figure below is from a page that was actually fetched. Cells marked **NOT PUBLISHED**
are gaps, not estimates. Nothing here is averaged or inferred.

| | Twilio (shipped) | Telnyx (evaluated) |
|---|---|---|
| **Spain landline /min** | $0.0178 (EEA origination) | $0.012 (in-country band) |
| **Spain mobile /min** | $0.0486 (EEA origination) | $0.028 (in-country band) |
| **Origination-CLI banding** | Yes — 3.7× penalty for non-EEA | Yes, harsher: catch-all landline band is **$0.4001** (33× the local band) |
| **Which band a +34 CLI hits** | Documented as EEA | **NOT PUBLISHED** — `34` appears in both the EEA list and the "local" band |
| **Billing increment** | 60/60 round-up | 60/60 round-up (verified across all 2,428 outbound rates) |
| **Browser leg /min** | $0.0040 | $0.002 |
| **Recording /min** | $0.0025 | $0.002 |
| **Recording storage** | $0.0005/min/mo, first 10,000 min free | $0/min base; $0.0004/min above 10,000 min |
| **Dual-channel WAV** | Yes — `record-from-answer-dual` | Yes — `channels: dual`, `format: wav`, explicit enums |
| **Disclosure to callee only** | `<Number url>` with `<Say>` — documented | Call Control play-to-leg-then-bridge — documented and unambiguous. TeXML `<Number url>` exists but only lists `<Gather>`/`<Hangup>` |
| **Browser SDK, no bundler** | UMD, 302 KB, `Twilio.Device` | UMD `lib/bundle.js`, 273,634 B, `globalThis.TelnyxWebRTC` — verified by executing it in a bare VM |
| **Browser token TTL** | 1 h, stateless JWT, not revocable | 24 h, revocable via `DELETE /v2/telephony_credentials/:id` |
| **Server-authoritative CLI** | TwiML App webhook + signature | "Park Outbound Calls" — browser leg is parked, backend dials PSTN with its own `from`, then bridges |
| **Webhook signature** | HMAC over **request URL** + body | Ed25519 over `timestamp\|body` — **URL not signed** |
| **ISV sub-accounts** | Self-serve, any tier | Managed Accounts are **Enterprise-only** ($5,000/mo published minimum) plus explicit Telnyx approval |
| **MV3 extension precedent** | We shipped it | **None found** — zero hits for manifest v3 / offscreen / service worker in the SDK repo |

### Where Telnyx is genuinely better

- **Minutes.** Roughly 42% cheaper to Spanish mobile, 33% cheaper to landline, half price on
  the browser leg — *if* a `+34` CLI lands in the in-country band, which is not published.
- **Webhook signatures don't include the URL.** Twilio's do, which is why we carry a
  configured public base URL to rebuild the signed URL behind our proxy. That whole class of
  bug disappears with Ed25519 over `timestamp|body`.
- **Recording can be written directly into our own bucket** via
  `POST /v2/custom_storage_credentials/{app_id}`. This removes the download hop, the 10-minute
  pre-signed URL race, and one credential we currently hold. It is strictly better than what
  we built, and it is the single most attractive thing in the whole evaluation.
- **Revocable browser tokens.** A 24 h TTL sounds worse than Twilio's 1 h until you notice
  Twilio's JWT cannot be revoked at all, and Telnyx's credential can.
- **An unauthenticated pricing API.** `GET api.telnyx.com/v2/pricing/products/elastic-sip-outbound?filter[country_iso]=ES`
  returns the real rate deck with no login and no sales call. Useful for cost modelling
  regardless of which carrier we use.

### Where Telnyx is worse, and it is disqualifying today

- **Short Duration surcharge.** Once more than 15% of a month's calls are ≤6 seconds, Telnyx
  applies **$0.01 per call retroactively to all of them**, and states plainly: "We do not
  support use cases that require Short Duration calls." SDR cold-dialling is *mostly*
  sub-6-second calls — unanswered, voicemail, immediate hangup. This targets our exact usage
  pattern, and it is the single strongest argument against Telnyx for this product.
- **Multi-tenancy is gated behind Enterprise.** Managed Accounts have better primitives than
  Twilio subaccounts — API-creatable, `rollup_billing`, per-tenant custom pricing — and are
  documented as "No access" at Pretrial, Trial, Paid *and* Verified tiers. We would be using
  Outbound Voice Profiles instead, which do not isolate caller IDs, precisely the thing we
  need isolated.
- **Concurrency ceiling.** Paid accounts are capped at 10 calls/hour. Fine for a pilot,
  meaningless for production, and lifting it means the sales conversation.
- **No MV3 precedent.** The UMD bundle checks out under inspection (0 occurrences of `eval` /
  `new Function`, no Node APIs, default MV3 CSP satisfied unrelaxed), but nobody has publicly
  run this SDK in a Chrome extension. Evidence is *absent*, not negative — we would be first,
  and that is schedule risk we cannot currently price.
- **Verified Numbers has no country documentation at all.** Not "US-only" like Twilio's
  folklore — genuinely undocumented. No narrative doc page exists; the API takes
  `phone_number` with no country field. Spanish verification is untested, and the whole point
  is now moot anyway.

## Caveats on the numbers

- **Our Twilio Spain figures were gathered under the BYO-CLI assumption.** They are EEA-
  origination rates. Under the remediated design the CLI becomes a carrier-provisioned Spanish
  number, so the origination band changes and both carriers' rates need re-checking before
  they go into a pricing model. Do not carry these forward unverified.
- **Telnyx prices Spanish mobile per terminating carrier**, so the in-country "mobile" band is
  a range ($0.0211–$0.0433 depending on band and carrier), not a single number. The effective
  blend can only come from our own CDRs.
- **Storage rounds each recording up to a full minute** on Twilio. On SDR dialling with a long
  tail of 5-second no-answers, that rounding dominates the storage line — the per-minute rate
  is misleading at our call-duration distribution.
- **Telnyx's storage tier semantics are unclear.** "$0/min base, first tier starts at 10,000
  min" does not state whether the 10,000 is monthly or cumulative. Get it in writing before
  modelling.
- **Telnyx publishes an automatic 8%/yr price escalator** in its T&Cs (§21.9). Twilio does not
  publish an equivalent. This inverts the cost advantage over a multi-year horizon and belongs
  in any TCO comparison.

## Edge cases worth writing down

These are the ones that will bite in production, on either carrier.

1. **A connected call is not a delivered caller ID.** Under Art. 5.2 a Spanish carrier may
   suppress or flag the CLI instead of dropping the call. Success in our logs, "Número
   privado" on the handset. Any acceptance test must check the handset display, not the call
   status.
2. **Per-carrier variance in Spain.** Movistar, Vodafone and Orange each implement their own
   roaming detection under Art. 5.2. Testing against one proves nothing about the others.
3. **Emergency numbers bypass Telnyx call parking** by design. If we ever adopt the parking
   model, the server-authoritative caller-ID guarantee has a documented hole at `112`/`911`.
   Block emergency numbers in the dialer rather than relying on the parking invariant.
4. **Telnyx custom headers are browser input.** `customHeaders` on `newCall` is the analogue
   of our TwiML POST params for CRM correlation, and like those params it is attacker-
   controlled. Same rule as today: the server must never trust it for authorization, only for
   correlation.
5. **Telnyx credential provisioning has a ~5 s settling delay** before first login. Provision
   credentials ahead of time; do not create one at click-to-call.
6. **Setting a Telnyx webhook URL reclassifies a call** from SIP trunking to programmable
   voice, which can anchor media further away in non-core regions. Latency regression with no
   obvious cause.
7. **The offscreen document is shared** with two other microphone features. Telnyx's README
   warns the session-level `remoteElement` is clobbered by the last call to connect — the
   per-call form is mandatory for us, not optional.
8. **Twilio's Transit Caller ID sunset was 2026-06-22**, not the 2026-05-31 that circulates in
   a widely-shared dev.to article. That date is two months past. Production call logs should
   be audited for rejections regardless of the redesign.
9. **Cross-account CLI reuse is undocumented on both carriers.** Whether the same E.164 can be
   verified on two accounts is unspecified, and it matters for multi-tenant: two of our
   customers could plausibly try to claim the same number.
10. **Verified caller ID caps are undocumented above trial** on both carriers. Twilio
    documents 5 on trial and says the cap is lifted on upgrade, without saying to what. Telnyx
    documents trial limits and a "reinforced KYC" threshold at 200 numbers. Neither publishes
    a production ceiling for a product where every SDR registers a number.

## False assumptions this investigation destroyed

Kept deliberately, because several of them are load-bearing in shipped code and in the
[implementation plan](../superpowers/plans/2026-08-26-vocify-outbound-calling.md).

| Assumption | Reality |
|---|---|
| SDRs can present their own number as CLI in Spain | Not viable. Art. 9.1 makes the mobile case sanctionable against our customer, Art. 4.4 causes partial silent delivery failure, and from 2026-10-17 the 400 range makes it structurally impossible for commercial calls |
| Art. 4.4 obliges every terminating carrier to block our calls | **Our own overstatement, corrected.** The duty fires only where the receiving operator holds that CLI as `asignado o portado` — same-operator combinations and transit, not all traffic. The result is a partial, silent, carrier-clustered failure rate, which is harder to detect than a clean block |
| Presenting your own number is illegal for us | **Our own overstatement, corrected.** Arts. 4 and 5 bind operators, not callers. We are not the sanctionable party; our *customer* is, under Art. 9 |
| B2B prospecting might be outside Art. 9 | Does not hold. Ley 11/2022 Anexo II defines `usuario` as `persona física o jurídica`, so a company is an end user, and Art. 9 has no consumer qualifier |
| 800/900 is the safe conservative fallback | Overtaken. From 2026-10-17 commercial calls must originate from 400, and 400 numbers cannot receive incoming calls, so the free-callback rationale disappears |
| Geographic numbering was the open legal question | It was, and it resolved in our favour — the Order is silent on 91x/93x, so it was permitted. Then the 400 resolution superseded the question entirely |
| The blocker is Twilio's Verified Caller ID being US-only | Twilio's docs contain no country restriction anywhere. The "US-only" claim traces to a single unsourced StackOverflow answer; the reporter was on a trial account with a documented 5-number cap, and the real cause was Geo Permissions |
| Moving to Telnyx would fix Spanish caller ID | It would not. Telnyx's own Spain page states the same prohibition |
| Not buying numbers avoids per-tenant KYC | KYC is the price of a legal Spanish caller ID. It cannot be designed around |
| Telnyx recording storage is free | Base rate is $0/min, but the first tier starts at 10,000 min and then charges $0.0004/min. Partially refuted |
| Telnyx would let us bill short SDR calls per second | 60/60 round-up on every one of 2,428 outbound rates, plus a $0.01/call surcharge aimed squarely at sub-6-second calls |
| Telnyx sub-accounts are the ISV answer | Managed Accounts are documented as "No access" below Enterprise, $5,000/mo plus Telnyx approval |
| Telnyx's WebRTC SDK would need a bundler | It ships a real UMD bundle that attaches a global — verified by executing it in a bare VM. This one turned out *better* than assumed |
| The Transit Caller ID sunset is 2026-05-31 | 2026-06-22, per Twilio's own changelog. The May date exists only in a third-party article that postdates and contradicts Twilio's announcement |
| Dual-channel recording bills at 2× | Confirmed 1×. Twilio's 2022 post: "dual-channel is now the same price as mono-channel storage." An older Twilio blog claiming 2× is stale |

## What to do next

1. **Commit to endpoint capture as the strategic path** (Option A). It removes the entire
   category of problem this investigation uncovered, and most of the technology already exists
   in the Companion app and the extension's offscreen document. Scope the work to make it the
   primary route for call audio rather than a secondary one.
2. **Stop offering BYO caller ID as the Spanish default.** Today an SDR can verify a personal
   mobile, get a 200, get billed, and have the call fail invisibly. Gate Spanish mobile ranges
   at verification time with an explanatory message.
3. **Legal, and the clock is running.** Two questions for a Spanish telecoms lawyer, both
   gating: does a B2B SaaS whose customers sell to businesses fall within Ley 10/2025's scope
   (which decides whether the 400 obligation binds them), and how does the Primero.2 versus
   Sexto contradiction in the SETID resolution resolve? Seven weeks to 2026-10-17.
4. **Check for a published SETID exception** under Arts. 4.6 / 5.3. None was found, but the
   search was not exhaustive, and it is an hour of work against a large payoff.
5. **Audit production call logs** against the 2026-06-22 Transit Caller ID sunset, which has
   already passed.
6. **Do not migrate to Telnyx.** Keep this folder current; revisit if the Short Duration
   surcharge changes, Managed Accounts come downmarket, or minute cost becomes the binding
   constraint.
7. **Steal one thing from Telnyx regardless:** direct-to-bucket recording delivery is a better
   design than our download-and-store hop. Check whether Twilio has an equivalent.

One thing worth internalising from how this went: we nearly migrated carriers on the strength
of an unsourced forum answer, and the question that actually mattered was answerable by reading
HubSpot's own country-support page. Check what the market leader ships before assuming a
constraint is technical.

Remediation sequencing is in
[`../superpowers/plans/2026-08-27-spain-cli-remediation.md`](../superpowers/plans/2026-08-27-spain-cli-remediation.md).
