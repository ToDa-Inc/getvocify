# Spain caller-ID remediation plan

> **For agentic workers:** this plan has a **blocking legal gate** (Phase 0). Do not start
> Phase 2 until Phase 0 returns an answer. Phases 0 and 1 are safe to execute now. Steps use
> checkbox (`- [ ]`) syntax.

**Supersedes the caller-ID model in**
[`2026-08-26-vocify-outbound-calling.md`](2026-08-26-vocify-outbound-calling.md). Everything
else in that plan — dialer, WebRTC leg, dual-channel recording, transcription, extraction,
HubSpot logging — stands unchanged.

**Why:** that plan's Global Constraint #14 says "Caller ID is always the user's own verified
number. Never a Twilio-purchased number. Outbound only — no number is rented, so no regulatory
bundle." In Spain that is prohibited. Two articles of
[Orden TDF/149/2025](../../telephony/regulatory/spain-cli-tdf149-2025.md) each independently
break it, neither with an exception for owning the number:

- **Art. 4.4** obliges a carrier to block a call presenting a CLI that carrier holds but did
  not originate. **Art. 4.5** makes this apply whether the call is domestic or international,
  which is what makes it carrier-independent.
- **Art. 9.1** prohibits mobile numbering ranges for unsolicited commercial calls, sanctionable
  against *our customer* under Art. 107.19 of Ley 11/2022.

Both in force since ≈2025-06-05.

**Not a carrier problem.** Telnyx was evaluated and rejected; see
[`../../telephony/DECISION.md`](../../telephony/DECISION.md). Its own Spain page states the
same prohibition. We stay on Twilio and change caller-ID sourcing.

**Goal:** an SDR clicks "Llamar" and the call goes out with a caller ID that is legal in Spain,
that the prospect can call back, and that actually displays on the handset — with every other
part of the pipeline untouched.

## The deadline

**2026-10-17.** [Resolución SETID de 14 de abril de 2026](https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8409),
apartado sexto: from six months after entry into force, *"las llamadas comerciales sólo podrán
efectuarse a través del rango NXY = 400 no pudiendo utilizarse desde entonces ningún otro rango
de numeración para la realización de llamadas comerciales."*

A 400 number is held by an operator, assigned by the CNMC (apartado cuarto.1), and **cannot
receive incoming calls** (apartado tercero.1). It can never be an SDR's own number. In Spain,
"present your own caller ID" and "make a commercial call" become mutually exclusive.

This also removes 800/900 as the conservative fallback — the free-callback rationale for
800/900 disappears when the permitted range cannot be called back at all.

## The strategic answer: stop being the carrier

The original goal was to own the conversation data rather than depend on Aircall's API. Owning
the data and originating the call are separable, and the plan they came from conflated them.
Spain has now moved three times in eighteen months, and HubSpot's country page documents CLI
restrictions in seven other jurisdictions. Chasing numbering regulation across 27 divergent
regimes buys no defensibility.

**Phase 2C (endpoint capture) is the recommended path** and is not gated on any legal answer.
Phases 2A/2B remain as tactical options for customers who want click-to-call before 2C lands.

## The gate (for the carrier-facing branches only)

Two questions, both needing a Spanish telecoms lawyer, both only relevant to 2A/2B:

1. **Does a B2B SaaS whose customers sell to businesses fall within Ley 10/2025's scope?**
   Apartado primero.2 limits the 400 exclusivity to *"las empresas comprendidas en el ámbito de
   aplicación de la citada Ley"* — Art. 2.2 of Ley 10/2025 covers firms selling
   *"destinados principalmente a personas consumidoras y usuarias"* above 250 staff / €50M
   turnover / €43M assets. A small B2B seller sits outside it.
2. **How does the Primero.2 / Sexto contradiction resolve?** Primero.2 is scoped; Sexto is
   unqualified. Nobody has resolved this. Practically, operators enforce the rule and cannot
   know a customer's legal scope, so whatever blocking they implement will be behaviour-based —
   and Ley 10/2025 Art. 16.4 reportedly permits blocking on `indicios` of commercial calling
   regardless of range, which would mean a landline does not help either.

Note what is **no longer** a gate: whether geographic 91x/93x numbering is permitted. It is —
the Order is silent on geographic ranges, so they were allowed. The 400 resolution superseded
the question.

## Out of scope

Migrating carriers. Number porting (option 3 in the regulatory doc — revisit only if a
customer specifically wants their existing landline moved). Markets other than Spain. Inbound
call handling on the new DIDs. Salesforce.

---

## Phase 0 — Unblock (no code)

Do these first; they are cheap and two of them can invalidate later work.

- [ ] **0.1 — Legal opinion on geographic numbering.** Brief a Spanish telecoms lawyer with
  the gate question above, plus the primary source
  ([BOE-A-2025-2870](https://www.boe.es/eli/es/o/2025/02/12/tdf149/con)) and our reading in
  [`../../telephony/regulatory/spain-cli-tdf149-2025.md`](../../telephony/regulatory/spain-cli-tdf149-2025.md).
  Ask specifically about Art. 9.1 scope versus Art. 10.1, and whether "llamadas comerciales no
  solicitadas" covers an SDR calling a prospect who is an existing marketing contact.
  **Verification:** written opinion naming the permitted ranges. Record it in the regulatory
  doc.

- [ ] **0.2 — Check for a published SETID exception.** Arts. 4.6 and 5.3 permit the Secretaría
  de Estado to except justified cases by resolution, notified to the CNMC and published on the
  SETID portal. Search the SETID portal and CNMC publications for anything covering cloud PBX
  or BYO-CLI. **This is the only path where the shipped design survives unchanged** — long
  shot, an hour of work, enormous payoff. **Verification:** either a citation to a covering
  exception, or a written note that none exists as of the search date.

- [ ] **0.3 — Audit production against the Transit Caller ID sunset.** Twilio's changelog gives
  2026-06-22 (not the 2026-05-31 that circulates in a third-party article), which is two months
  past. Query call logs for rejections attributable to non-Twilio, non-verified caller IDs.
  **Verification:** a count of affected calls, and confirmation of whether we are currently
  failing in production.

- [ ] **0.4 — Re-price under the new model.** The Spain rates in the existing runbook are
  EEA-*origination* rates gathered under the BYO-CLI assumption. With a carrier-provisioned
  Spanish DID the origination band changes. Re-fetch Twilio's Spain rates for Spanish-
  origination, and recompute cost per call including the storage-rounding effect (each
  recording rounds up to a full minute, which dominates at SDR call-duration distributions).
  **Verification:** an updated cost table in
  [`../../runbooks/twilio-setup.md`](../../runbooks/twilio-setup.md).

---

## Phase 1 — Stop shipping something that cannot work (code, no gate)

Safe to execute now regardless of the gate outcome. The current UI invites SDRs to verify a
personal Spanish mobile, which is prohibited and will fail silently.

- [ ] **1.1 — Gate Spanish mobile verification in the UI and API.** In
  `backend/app/services/telephony/caller_id.py`, reject `start_caller_id_verification` for
  `+34` numbers in mobile ranges (6xx/7xx) with an explanatory error rather than calling
  Twilio. Surface it in the side panel with copy explaining the legal reason, not a generic
  failure. Mirror the range check in `chrome-extension/lib/dialer.js` so the UI can warn before
  a round trip.
  **Rationale:** an SDR who verifies a mobile today gets a 200, a `CallSid`, a bill, and a call
  that is blocked at the Spanish interconnect. Failing loudly at verification time is far
  cheaper than failing invisibly at call time.
  **Verification:** `cd backend && python -m pytest tests/test_telephony_caller_id.py -v` with
  new cases for `+34 6xx`, `+34 7xx`, `+34 91x`, and a non-Spanish number (must still pass).
  `cd chrome-extension && node --test lib/dialer.test.js`.

- [ ] **1.2 — Add CLI delivery observability.** Under Art. 5.2 a Spanish carrier may deliver a
  call with the CLI **suppressed or flagged unverified** instead of blocking it — so the call
  connects and our telemetry looks perfect while the prospect sees "Número privado". Record per
  call: the caller ID we requested, Twilio's final call status, and the disposition. Without
  this, a CLI-delivery failure is indistinguishable from a bad contact list.
  **Verification:** place a test call, confirm the requested caller ID and status are persisted
  on the `outbound_calls` row.

- [ ] **1.3 — Block emergency numbers in the dialer.** `112`, `061`, `091`, `092`. Not a
  regulatory requirement for us, but an SDR mis-dial routes an emergency call with a
  commercial caller ID, and on some carrier models emergency numbers bypass caller-ID
  controls entirely.
  **Verification:** `node --test lib/dialer.test.js` with cases for each number, bare and with
  `+34`.

- [ ] **1.4 — Correct the falsified constraints in the shipped plan.** Add a prominent note at
  the top of [`2026-08-26-vocify-outbound-calling.md`](2026-08-26-vocify-outbound-calling.md)
  pointing at this plan and at the false-assumptions table in
  [`../../telephony/DECISION.md`](../../telephony/DECISION.md). Do not rewrite the plan's body
  — it is an accurate record of what was built and why, and the reasoning error is more useful
  visible than erased.
  **Verification:** the note names Global Constraint #14 explicitly.

---

## Phase 2A — Geographic DIDs *(only if 0.1 permits geographic numbering)*

- [ ] **2A.1 — Provisioning model.** Decide DID granularity: one per tenant, or one per SDR.
  Per-SDR gives each rep a callback number and a cleaner story; per-tenant is cheaper and has
  one regulatory bundle. Area code should match the tenant's registered address — Twilio's
  Spanish geographic numbers require an address matching the DID's area code.
  **Verification:** a written decision with the cost per tenant per month at both granularities.

- [ ] **2A.2 — Regulatory bundle onboarding.** Per-tenant KYC: CIF or DNI/NIE, proof of address
  matching the area code, dated within the carrier's window. This is now a step in customer
  onboarding, not a hidden implementation detail — it needs an owner, an SLA, and a status the
  tenant can see. Twilio's regulatory bundle API supports programmatic submission; check
  whether it covers Spain before designing a manual flow.
  **Verification:** one bundle submitted and approved end to end for a real tenant.

- [ ] **2A.3 — Schema and resolution changes.** `user_caller_ids` currently models
  "user-verified external number" (`twilio_validation_sid`, verification status machine). It
  now needs to model "carrier-provisioned DID adjudicated to a tenant" — a different lifecycle
  with no verification step. Decide whether to extend the table with a kind discriminator or
  add a sibling table, then update `resolve_caller_id` to prefer a provisioned DID and fall
  back to a verified external number only for non-Spanish destinations.
  **Rationale:** `resolve_caller_id` is the single server-side authority for caller ID
  (`caller_id.py:148-175`); keeping it the only resolution point preserves the security
  property that the browser cannot choose its own CLI.
  **Verification:** `pytest tests/test_telephony_caller_id.py -v`, including a case asserting
  a Spanish destination never resolves to an external verified number.

- [ ] **2A.4 — Verify delivery on real Spanish networks.** Place calls to Movistar, Vodafone
  and Orange, on both mobile and landline destinations, and **check what the handset displays**
  — not the call status. Each carrier implements its own Art. 5.2 roaming detection and they
  will not behave identically. Connection success is not evidence of compliance.
  **Verification:** a table of carrier × destination-type × displayed CLI, with screenshots.

- [ ] **2A.5 — UX copy.** The side panel currently says the caller ID is the SDR's own verified
  number. Rewrite to explain the provisioned number and why. Spanish copy, accents intact —
  the existing `<Say>` strings had accents stripped once already and it changes pronunciation.
  **Verification:** manual review of the side panel and the recording-disclosure TwiML.

---

## Phase 2B — 800/900 numbering *(only if 0.1 restricts to 800/900)*

Same shape as 2A with three differences:

- [ ] **2B.1 — Provisioning.** 800/900 are non-geographic, so there is no area-code/address
  matching constraint. Art. 10.3 authorises their use as CLI generally, and Art. 10.2 keeps
  callbacks free for the prospect. Simpler than 2A. Confirm Twilio sells Spanish 800/900 and
  what its regulatory requirements are — **do not assume it does**; non-geographic Spanish
  ranges are not always offered by international carriers.
  **Verification:** a purchasable number confirmed in the Twilio console or API.

- [ ] **2B.2 — Inbound handling is now mandatory, not optional.** The entire point of 800/900
  under Art. 10 is that the prospect can call back for free. A callback that rings nowhere is
  worse than no callback number. Inbound was explicitly out of scope in the original plan; this
  branch pulls it in.
  **Verification:** a callback to the 800/900 number reaches the SDR or a defined destination.

- [ ] **2B.3 — Answer-rate expectation.** 800/900 CLIs are widely recognised in Spain as
  commercial and are answered less. This is a product risk, not an engineering one, and it
  should be stated explicitly to whoever owns the roadmap before the branch is built.
  **Verification:** the risk is written down and acknowledged.

Then 2A.3, 2A.4 and 2A.5 apply unchanged.

---

## Phase 2C — Endpoint capture *(recommended; not gated)*

Make Vocify's call audio come from the endpoint rather than from the carrier. This is the path
that dissolves the problem instead of tracking it.

- [ ] **2C.1 — Inventory what already exists.** `desktop/` (Companion) already captures mic plus
  system audio Granola-style, and `chrome-extension/offscreen.js` already does tab capture with
  `USER_MEDIA` and `AUDIO_PLAYBACK`. Establish precisely which call scenarios are already
  covered today and which are not: browser softphone in a tab, native desktop softphone
  (Aircall/Ringover desktop app), desk phone, mobile on speaker.
  **Verification:** a coverage matrix with a real capture test per row.

- [ ] **2C.2 — Close the softphone gap.** The highest-value scenario is an SDR calling from a
  native softphone while Companion captures system audio plus mic. Confirm this produces two
  usable channels — the extraction pipeline wants speaker separation, and the existing
  `record-from-answer-dual` path got that from the carrier for free. Determine whether mic and
  system audio can be kept on separate channels through to `stt_batch`, or whether diarisation
  has to do the work instead.
  **Rationale:** this is the one genuine technical risk in Phase 2C. Carrier dual-channel
  recording is cleanly separated by construction; endpoint capture is not, unless we keep the
  two sources apart deliberately.
  **Verification:** a captured softphone call transcribed with correct speaker attribution,
  compared against the same call recorded through the Twilio path.

- [ ] **2C.3 — Consent and disclosure.** Recording moves from carrier-side (where the TwiML
  whisper played a Spanish disclosure to the callee) to endpoint-side, where we cannot inject
  audio into the far leg. The disclosure obligation does not disappear — it becomes the SDR's
  to deliver, and ours to prompt and evidence. Design the prompt and the audit record.
  **Rationale:** this is a real regression versus the carrier path and must not be discovered
  after launch. It is a data-protection obligation, not a numbering one, but it is the one part
  of Phase 2C that is harder than the status quo.
  **Verification:** documented consent flow reviewed against AEPD guidance, with a per-call
  audit record.

- [ ] **2C.4 — Correlate the captured call to a CRM record.** The carrier path got the contact
  id from the dial action. Endpoint capture has no such signal — the SDR just talks. Options:
  the extension already detects HubSpot page context, Companion could take an explicit
  selection, or match on recency. Decide, and prefer explicit over inferred.
  **Verification:** captured calls land on the right contact without manual correction in a
  realistic session.

- [ ] **2C.5 — Position the dialer.** Keep it. In markets where BYO-CLI works it is a real UX
  win, and with a provisioned DID it works in Spain until October. Change the framing so the
  data path does not depend on it.
  **Verification:** the product surface makes clear that call intelligence works regardless of
  how the call was placed.

## Phase 3 — Worth doing regardless of branch

- [ ] **3.1 — Evaluate direct-to-bucket recording delivery.** Telnyx writes recordings straight
  into a customer-owned bucket (`POST /v2/custom_storage_credentials/{app_id}`), removing the
  download hop, the pre-signed-URL race, and one credential. That is strictly better than our
  download-and-store path in `call_processor.py:44-47`. Check whether Twilio offers an
  equivalent before building anything further on the current path.
  **Verification:** a documented yes/no with a URL.

- [ ] **3.2 — Document the undocumented ceilings.** Neither carrier publishes a production cap
  on verified caller IDs, and cross-account reuse of the same E.164 is unspecified on both. For
  a multi-tenant product where every SDR registers a number, both are real scaling risks. Get
  answers from Twilio support in writing.
  **Verification:** written answers recorded in
  [`../../telephony/twilio/assumption-audit.md`](../../telephony/twilio/assumption-audit.md).

---

## Reference

| Document | Use |
|---|---|
| [`../../telephony/DECISION.md`](../../telephony/DECISION.md) | Carrier decision, caveats, edge cases, false assumptions |
| [`../../telephony/regulatory/spain-cli-tdf149-2025.md`](../../telephony/regulatory/spain-cli-tdf149-2025.md) | The law, read against our design, from the BOE |
| [`../../telephony/portability/carrier-coupling-audit.md`](../../telephony/portability/carrier-coupling-audit.md) | What is Twilio-coupled, with line counts — for if a carrier move is ever revisited |
| [`../../telephony/telnyx/`](../../telephony/telnyx/) | Telnyx reference, and the three designs worth stealing |
| [`2026-08-26-vocify-outbound-calling.md`](2026-08-26-vocify-outbound-calling.md) | What was built. Constraint #14 is now known false |
