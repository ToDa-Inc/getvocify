# Telnyx research: Spain outbound click-to-call pricing + ISV multi-tenancy

Research date: 2026-08-27. All figures below were read directly off a Telnyx-owned page or a
Telnyx-owned public API response. Nothing is estimated, averaged, or inferred. Where a figure
is not published, the cell says **NOT PUBLISHED** and states where it would have to come from.

Use case being priced: browser (WebRTC) leg bridged to a PSTN leg, outbound to Spain, caller ID
is the SDR's own verified number (no rented numbers), dual-channel recording + transcription.

---

## 0. The single most important discovery: Telnyx has a public, unauthenticated pricing API

`https://telnyx.com/pricing.md` (Telnyx's own machine-readable pricing endpoint) states verbatim:

> "Every rate is read live from the public pricing API
> (`GET https://api.telnyx.com/v2/pricing/products/{slug}`) — the same source
> the /pricing/\* pages render, cached for at most 24 hours."

and

> "Outbound calling is priced by destination and is not listed here — see
> https://telnyx.com/pricing/elastic-sip. Items marked "Rate deck" are priced the same way."
> "Deliberately not listed: `elastic-sip-outbound` (priced by destination — see /pricing/elastic-sip)."

The `elastic-sip-outbound` slug **is** queryable on that API without any API key:

```
curl "https://api.telnyx.com/v2/pricing/products/elastic-sip-outbound?filter[country_iso]=ES&page[number]=1"
```

It returns 2,428 outbound rate rows globally (34 for Spain), each with:
`iso`, `country`, `origination_prefixes`, `description`, `interval_1`, `interval_n`, `rate`,
`price_per_call`, `exact_match`.

This means Spain outbound rates **are published** and machine-readable. No sales quote, no login,
no rate-sheet email gate required. Pagination is `page[number]`, `page[size]` (max 100).

---

## 1. Spain outbound termination

### 1a. What the human-readable pricing page shows

On `https://telnyx.com/pricing/elastic-sip`, setting the country selector to **Spain** renders,
under "Make outbound calls", a two-row table (verified by direct browser interaction, screenshot
at `/var/folders/bh/c40d703s6573gphxfgf9t5gm0000gn/T/cursor/screenshots/spain-outbound-pricing.png`):

| Label rendered on page | Rate rendered on page |
|---|---|
| Local - Fixed | **$0.012 per minute** |
| Local - Mobile | **$0.028 per minute** |

It is a real two-row rate table, not a "starting at" figure. The page does **not** surface any
origination-based variants ("From EEA" / "Non Surcharged") in that view. Inbound for Spain on the
same page shows "Local calls: Starting at $0.008 per minute" and "Toll-free calls: Starting at
$0.012 per minute*".

Note that the two rows the website shows correspond exactly to the API rows whose
`origination_prefixes` field equals the literal string `"local"`. In other words, the public
website surfaces only the **in-country-CLI (origination = Spanish number)** rate band.

### 1b. Full published Spain matrix from the pricing API (all 34 rows)

Telnyx groups Spain outbound rates into **four origination bands**, keyed by the
`origination_prefixes` field. This is Telnyx's direct structural equivalent of Twilio's
EEA-vs-non-EEA origination surcharge, and it is materially more granular than Twilio's.

**Band A — `origination_prefixes: "local"`** (this is the band the website shows)

| Description (verbatim) | Rate USD/min |
|---|---|
| Trunking Outbound Minute - Spain - Fixed - Local | 0.012 |
| Trunking Outbound Minute - Spain - Mobile - Local | 0.028 |
| Trunking Outbound Minute - Spain - Freephone - Local | 0.0 |
| Trunking Outbound Minute - Spain - NGN Service 1 - Local | 0.012 |
| Trunking Outbound Minute - Spain - NGN Service 2 - Local | 0.15 |
| Trunking Outbound Minute - Spain - NGN Service 3 - Local | 0.62 |

**Band B — `origination_prefixes: "30, 31, 32, 33, 34, 351, 352, 353, 354, 356, 357, 358, 359, 36, 370, 371, 372, 385, 386, 39, 40, 420, 421, 423, 43, 45, 46, 47, 48, 49"`** (labelled "From EEA"; note `34` = Spain is in this list)

| Description (verbatim) | Rate USD/min |
|---|---|
| Trunking Outbound Minute - Spain - From EEA (fixed/landline) | 0.0118 |
| Trunking Outbound Minute - Spain - Mobile - From EEA | 0.0211 |
| Trunking Outbound Minute - Spain - Mobile Lycatel - From EEA | 0.0211 |
| Trunking Outbound Minute - Spain - Mobile Orange - From EEA | 0.0211 |
| Trunking Outbound Minute - Spain - Mobile Telefonica Spain - From EEA | 0.0284 |
| Trunking Outbound Minute - Spain - Mobile Vodafone - From EEA | 0.0306 |
| Trunking Outbound Minute - Spain - Mobile Xfera - From EEA | 0.0392 |
| Trunking Outbound Minute - Spain - Nomadic - From EEA | 0.57 |
| Trunking Outbound Minute - Spain - Special Non Geographic - From EEA | 0.6483 |
| Trunking Outbound Minute - Spain - Special Services - From EEA | 0.0153 |

**Band C — `origination_prefixes: "212, 298, 299, 350, 376, 380, 41, 51, 52, 54, 55, 56, 57, 590, 594, 596, 60, 61, 64, 65, 673, 81, 82, 852, 86, 880, 886, 91, 972, 976"`** (labelled "Non Surcharged"; this is a named list of **non**-EEA origination countries)

| Description (verbatim) | Rate USD/min |
|---|---|
| Trunking Outbound Minute - Spain - Non Surcharged (fixed/landline) | 0.0123 |
| Trunking Outbound Minute - Spain - Mobile - Non Surcharged | 0.0221 |
| Trunking Outbound Minute - Spain - Mobile Lycatel - Non Surcharged | 0.0221 |
| Trunking Outbound Minute - Spain - Mobile Orange - Non Surcharged | 0.0221 |
| Trunking Outbound Minute - Spain - Mobile Telefonica Spain - Non Surcharged | 0.0298 |
| Trunking Outbound Minute - Spain - Mobile Vodafone - Non Surcharged | 0.0322 |
| Trunking Outbound Minute - Spain - Mobile Xfera - Non Surcharged | 0.0413 |
| Trunking Outbound Minute - Spain - Special Services - Non Surcharged | 0.6498 |
| Trunking Outbound Minute - Spain - Special Services - Non Surcharged | 0.68 |

**Band D — `origination_prefixes: null`** (catch-all / no matching origination band)

| Description (verbatim) | Rate USD/min |
|---|---|
| Trunking Outbound Minute - Spain (fixed/landline) | **0.4001** |
| Trunking Outbound Minute - Spain - Mobile | 0.0233 |
| Trunking Outbound Minute - Spain - Mobile Lycatel | 0.0233 |
| Trunking Outbound Minute - Spain - Mobile Orange | 0.0233 |
| Trunking Outbound Minute - Spain - Mobile Telefonica Spain | 0.0314 |
| Trunking Outbound Minute - Spain - Mobile Vodafone | 0.0338 |
| Trunking Outbound Minute - Spain - Mobile Xfera | 0.0433 |
| Trunking Outbound Minute - Spain - Special Services | 0.6823 |
| Trunking Outbound Minute - Spain - Special Services | 0.9 |

### 1c. Does Telnyx differentiate by origination CLI the way Twilio does?

**Yes — and more aggressively than Twilio, but in the opposite direction for our case.** The
`origination_prefixes` field is an explicit CLI-country gate. Twilio's model is a single
EEA/non-EEA split (Twilio charges 3.7x more for non-EEA origination into Spain). Telnyx's model
has four bands (`local`, EEA prefix list, a named non-EEA prefix list, and a null catch-all).

The important asymmetry: for **Spanish landline** destinations the Telnyx catch-all (Band D)
is **$0.4001/min** versus **$0.012/min** for `local` — a 33x penalty, far worse than Twilio's
3.7x. For **Spanish mobile** the bands are all clustered between $0.0211 and $0.0433, so
mis-banding on mobile is comparatively cheap.

**IMPORTANT UNRESOLVED AMBIGUITY (do not paper over this in a model):** our SDR caller ID is a
Spanish `+34` number. `34` appears in Band B's prefix list *and* Band A is the `"local"` band
(origination country == destination country). Telnyx does **NOT PUBLISH** the band-selection
precedence rule anywhere I could find. Evidence that Band A is the one that applies: the Telnyx
website, when you select Spain, renders exactly and only the Band A rows. That is Telnyx's own
presentation choice and is the strongest available signal, but it is a presentation inference,
not a published rule. To resolve it definitively you would need either (a) a written statement
from Telnyx sales/support, or (b) an empirical test call from a `+34` CLI and then reading the
resulting CDR `cost` field. Do not model this from the two candidate numbers by picking one
silently — model both and flag it.

For a landline-heavy Spanish SDR motion the band question is worth 33x, so it is the single
highest-value open item in this research.

### 1d. Mobile carrier granularity

Telnyx prices Spanish mobile **per terminating mobile carrier** (generic, Lycatel, Orange,
Telefonica, Vodafone, Xfera), so effective mobile cost depends on the MNP-resolved carrier of
each dialled number. Twilio (per the figures supplied) publishes a single blended Spanish mobile
rate. The Telnyx **blend depends on your list's carrier mix and is therefore NOT PUBLISHED** —
it can only come from your own CDRs after you dial, or from a carrier-mix assumption you supply
yourself. Published spread: Band A gives one flat $0.028; Band B spans $0.0211–$0.0392.

### 1e. Rate sheet download

Both `https://telnyx.com/pricing/call-control` and `https://telnyx.com/pricing/elastic-sip`
contain a "Download SIP Trunking pricing" / "Download pricing" widget. In the fetched HTML this
renders as `Loading` — it is a client-side form. Whether it is email-gated was **not verified**.
Given that the same data is available unauthenticated from
`api.telnyx.com/v2/pricing/products/elastic-sip-outbound`, the download is not needed.

---

## 2. Billing increments

**Telnyx rounds up to the whole minute, with a 60-second minimum. Same as Twilio. Telnyx is
NOT per-second for this traffic.**

Two independent published sources:

1. **Pricing API, per-rate fields.** Every one of the **2,428** `elastic-sip-outbound` rate rows
   returns `"interval_1": 60, "interval_n": 60`. I checked the full paginated set: the
   distribution of `(interval_1, interval_n)` is `{(60, 60): 2428}` — there is not a single
   non-60/60 row, and the list of countries with a non-60/60 interval is empty. All 34 Spain
   rows are 60/60. `interval_1` = first billing increment in seconds, `interval_n` = subsequent
   increments in seconds.
2. **Terms and Conditions of Service, §12.1** (`https://telnyx.com/terms-and-conditions-of-service`),
   verbatim: *"All calls to the U.S. and Canada are billing in sixty second increments with a
   sixty second minimum."*

Caveat on source 2: the T&C sentence names only the U.S. and Canada. It does **not** state the
increment for Spain. The Spain-specific evidence is source 1 (the `interval_1`/`interval_n`
fields on the Spain rate rows themselves), which is a Telnyx-owned live API. I consider that
sufficient to state Spain is 60/60, but if you need contractual language for Spain specifically
that is **NOT PUBLISHED** and would have to come from a Service Order or written confirmation.

### 2a. Short Duration Call surcharge — directly relevant to SDR dialling

This is a Telnyx-specific cost that has no equivalent in the Twilio figures you supplied, and it
targets exactly the traffic profile an SDR dialer produces.

- Definition, from T&C §12.1 verbatim: *"A 'Short Duration' call is a call that is six (6)
  seconds or less in duration... Short Duration traffic is subject to a surcharge of $0.01 per
  call, in addition to all other applicable charges. Short Duration traffic may be moved by
  Telnyx to an alternate platform or blocked, in Telnyx's sole discretion."*
- Threshold, from `https://support.telnyx.com/en/articles/1130707-what-are-short-duration-calls`:
  15% of total monthly traffic is allowed. Above 15% for the calendar month, the $0.01/call
  penalty applies to **ALL** short duration calls that month, not just those above the 15% mark.
  International destinations included since 1 Jan 2024.
- Same article, verbatim: *"We do not support use cases that require Short Duration calls through
  our network."*
- Confirmed in the pricing API: `sip-trunking` product contains
  `"Global Conversational Short Duration Calls Surcharges, units: SDC Count"` at **$0.01 per
  call_count**, `type: surcharge`.
- Telnyx exposes a metric for self-monitoring: `usage_reports` with
  `dimensions=short_duration_call,direction`.

Also published: `"High Percentage of Abandoned Calls Surcharge, units: abandoned calls count"`
at **$0.005 per call**, `type: surcharge` (`sip-trunking` product).

### 2b. CPS surcharge — does NOT apply to this use case

`https://support.telnyx.com/en/articles/7834487-calls-per-second-cps-surcharges` publishes a
graduated monthly 95th-percentile peak-CPS surcharge (first 5 CPS free; up to 25 CPS $12/CPS;
up to 200 CPS $16/CPS; up to 250 CPS $24/CPS; 251+ CPS $30/CPS). Crucially, the article states
the excluded traffic includes **"Programmable Voice / Call Control traffic"**. A click-to-call
product built on the Voice API / Call Control is therefore outside the CPS surcharge. The
pricing API also lists `"CPS Peak Surcharge for Outbound Usage, units: CPS Count"` at **$0.0**.

Real-time CPS limit (separate mechanism, same article): standard SIP Trunking traffic is limited
to **20 CPS per source IP address or SIP username** by default; excess is rejected `503 CPS Limit
Reached (P05)`.

---

## 3. WebRTC / browser leg

**The WebRTC leg is billed separately, at $0.002/min. It is not free.**

- `https://developers.telnyx.com/docs/voice/webrtc/sdk-commonalities.md`, section "Costs",
  verbatim: *"WebRTC call legs are billed at $0.002/minute. Other voice legs and add on features
  are charged separately and independently according to the user's price plan."*
- `https://telnyx.com/pricing/call-control`, Optional features: **"Browser/app calling —
  $0.002 per minute"**.

Compare: your researched Twilio browser (client) leg figure is $0.0040/min. Telnyx's published
browser leg is $0.002/min — half.

### 3a. PSTN leg composition

`https://telnyx.com/pricing/call-control` states, verbatim: **"Make outbound calls — $0.002 per
minute + the SIP Trunking fee for outbound calls"**, and the FAQ on the same page states:

> "Telnyx Voice API calls utilize Telnyx Elastic SIP Trunks. By the nature of SIP Trunking, all
> calls are local calls, so you'll always be charged the local rate for dialing local prefix
> numbers, no matter where they are in the world."

The pricing API `voice-api` product confirms both directions as separate line items:
`"Call Control Origination Usage Cost - amount is per minute"` **$0.002/min** and
`"Call Control Termination Usage Cost - amount is per minute"` **$0.002/min**.

So the published components for one Spain click-to-call minute are:

| Component | Published rate | Source |
|---|---|---|
| Browser/WebRTC leg | $0.002/min | call-control pricing page + WebRTC docs |
| Voice API (Call Control) platform fee on the PSTN leg | $0.002/min | call-control pricing page + `voice-api` API |
| Spain trunking termination (Band A landline) | $0.012/min | elastic-sip page + `elastic-sip-outbound` API |
| Spain trunking termination (Band A mobile) | $0.028/min | elastic-sip page + `elastic-sip-outbound` API |

**NOT PUBLISHED / genuine ambiguity:** whether the browser leg *also* attracts a separate
`Call Control Origination Usage Cost` $0.002/min on top of the $0.002/min "Browser/app calling"
charge, i.e. whether a bridged 2-leg click-to-call incurs $0.002 (browser) + $0.002 (Call
Control on PSTN leg) = $0.004/min of platform fee, or $0.006/min. The WebRTC doc's sentence
"Other voice legs and add on features are charged separately and independently" implies the
former but does not say it. Resolve via a test call and reading the CDR/usage report `cost`
breakdown, or via written confirmation from Telnyx.

### 3b. Is SIP-to-SIP or WebRTC-to-Telnyx free?

**No published statement that it is free, and the published line items indicate it is not.**
I searched the full Telnyx "Calling" documentation corpus
(`https://developers.telnyx.com/docs/development/llms/calling-llms-full-txt`, 1.09 MB) for
"on-net", "Telnyx to Telnyx", "SIP to SIP", "free of charge", "no charge" — the only "on-net"
hit is about STIR/SHAKEN `verstat` scope, not billing. The relevant published charges are:

| Item | Published rate | Source |
|---|---|---|
| SIP interface | $0.002/min | `https://telnyx.com/pricing/call-control` |
| SIP URI Origination | $0.002/min | pricing API, `sip-trunking` product |
| SIP Subdomain Usage Cost | $0.002/min | pricing API, `sip-trunking` product |
| SIPREC client | $0.002/min | pricing API, `voice-api` product |
| Secure media | Free | `https://telnyx.com/pricing/call-control` |
| Call concurrency | Free | `https://telnyx.com/pricing/elastic-sip` |
| Secure trunking | Free | `https://telnyx.com/pricing/elastic-sip` |
| Toll-free outbound calls (US) | Free | `https://telnyx.com/pricing/elastic-sip` |

Conclusion: **a free on-net / SIP-to-SIP tier is NOT PUBLISHED.** If you need it, it would have
to come from a sales quote.

---

## 4. Recording and storage

**Your prior belief that Telnyx recording storage is free is CONFIRMED by published sources —
but confirmed on the specific metric "call recording storage, per minute", not as a blanket
"all storage is free" claim.**

| Item | Published rate | Source |
|---|---|---|
| Call recording | **$0.002 per minute** | `https://telnyx.com/pricing/call-control` and `https://telnyx.com/pricing/elastic-sip` (both pages, identical) |
| Call recording storage | **$0 per minute** | Both pages, verbatim "Call recording storage — $0 per minute" |
| `Cost associated with recording audio during an origination call - amount is per minute` | $0.002/min | pricing API, `voice-api` product |
| `Cost associated with recording audio during an termination call - amount is per minute` | $0.002/min | pricing API, `voice-api` product |
| `Cost associated with storage of a call recording - amount is per minute` | **$0.0/min** | pricing API, `voice-api` product |
| `Media storage - cost per API call` | $0.0/event | pricing API, `storage` product |
| Decrypted Forking | $0.0025/min | `https://telnyx.com/pricing/call-control` |
| Media Streaming over WebSockets | $0.0035/min | `https://telnyx.com/pricing/call-control` |

Compare to your Twilio figures: recording $0.0025/min and storage $0.0005/min/month (first
10,000 min free). Telnyx publishes recording at $0.002/min and recording storage at $0 with no
stated free-tier cap and no stated month-over-month accrual.

### 4a. Caveats you must not lose

- **Two recording line items exist** (origination-leg recording and termination-leg recording),
  each $0.002/min. Whether recording a bridged 2-leg click-to-call bills once or twice is
  **NOT PUBLISHED**. Resolve with a test call + CDR.
- **Retention period for free recording storage is NOT PUBLISHED.** I found delete endpoints
  (`DELETE /v2/recordings/:id`, bulk delete, transcription delete) but no published retention
  window or auto-expiry policy. Would have to come from support or the Service Order.
- **Dual-channel recording is supported and is a first-class config field**, at no separately
  published surcharge: the Outbound Voice Profile schema
  (`https://developers.telnyx.com/api-reference/outbound-voice-profiles/create-an-outbound-voice-profile`)
  contains `call_recording.call_recording_channels: dual`, `call_recording_format: mp3`, and
  `call_recording_type: by_caller_phone_number` with
  `call_recording_caller_phone_numbers: ["+19705555098"]`. That last field is notable for your
  design: recording can be triggered *by SDR caller ID*.
- **Telnyx Cloud Storage (a separate product, if you export recordings to your own bucket) has a
  published-source conflict.** `https://telnyx.com/pricing/storage` shows **$0.012 per GB**. The
  pricing API `storage` product shows `Storage for cloud storage product, charge is per GB per
  month` = **$0.0/GB/mo** (default region), `...in EU region` = **$0.025/GB/mo**, `...in APAC
  region` = **$0.025/GB/mo**. The `/pricing/call-control` page's cross-link says "Storage pricing
  Starting at $0.006 per GB". Three different published numbers. **Do not pick one.** Which
  applies to a Spain/EU-resident deployment is unresolved; treat as NOT RELIABLY PUBLISHED and
  confirm with Telnyx. (This only matters if you export off Telnyx media storage; native call
  recording storage is separately published at $0.)

### 4b. Transcription (you said calls are transcribed)

All from `https://telnyx.com/pricing/call-control`:

| STT provider | Published rate |
|---|---|
| Parakeet | $0.0015/min |
| Cohere Arabic | $0.0015/min |
| Soniox | $0.002/min |
| Grok (xAI) | $0.0033/min |
| Speechmatics | $0.0035/min |
| AssemblyAI | $0.007/min |
| Humain | $0.007/min |
| Basira | $0.007/min |
| Deepgram Nova 2 / Nova 3 / Flux | $0.0074/min |
| Telnyx STT | $0.015/min |
| Google | $0.017/min |
| Azure | $0.027/min |

---

## 5. Minimums, commitments, platform fees, trial credit

| Item | Published value | Source |
|---|---|---|
| Pay-as-you-go minimum commitment | **$0/mo**, "No minimum commitment", "All products available", community support, standard rate limits | `https://telnyx.com/pricing.md` → Plans → Pay-as-you-go |
| Committed plan minimum | **$500/mo** — volume discounts, dedicated AM, priority support, higher rate limits, custom SLA | same |
| Enterprise plan minimum | **$5,000/mo** — custom pricing, dedicated infra, 24/7 premium support, unlimited rate limits, custom SLA with credits, dedicated IP addressing, private network interconnect | same |
| Monthly platform fee to access voice / WebRTC | **None published.** No platform-fee line item appears on either voice pricing page, and PAYG is stated as $0/mo minimum. | `https://telnyx.com/pricing/call-control`, `https://telnyx.com/pricing/elastic-sip`, `pricing.md` |
| Committed-spend requirement to access verified numbers | **None published** | — |
| Pretrial account testing credit | **USD $25 in AI credits** | `https://developers.telnyx.com/docs/account-setup/levels-and-capabilities/pretrial.md` |
| Trial account testing credit | **USD $5 in testing credit** | `https://developers.telnyx.com/docs/account-setup/levels-and-capabilities/trial.md` |
| Default PAYG rate limits | SMS 50/sec, Voice 500 concurrent, API 100/sec | `https://telnyx.com/pricing.md` → Rate Limits |
| Automatic annual price escalator | **8% per annum increase adjustment** applied automatically to all fees and charges unless Telnyx designates otherwise in writing | T&C §21.9, verbatim: *"all fees and charges hereunder shall automatically be subject to an eight (8) percent per annum increase adjustment"* |
| Business Associate Agreement (HIPAA) MRC | $2,500/mo | pricing API, `account-services` product |
| Support services minimum commitment MRC | $10,000/mo | pricing API, `account-services` product |
| Support services usage-based upcharge | $10,000 | pricing API, `account-services` product |
| Inbound SIP channel pricing (only if you buy channels instead of per-minute inbound) | First 10 channels $12/mo each; next 40 $11; next 200 $9; 250+ $8 | `https://telnyx.com/pricing/elastic-sip` |
| Volume-discount rate card | **NOT PUBLISHED.** Pages only say "Receive a discounted rate with the more you spend". Must come from a sales quote. | — |

### 5a. Account-level gates that are a bigger problem than any fee

These are hard published limits by account level, and they matter a lot for an SDR dialer. Source:
`https://developers.telnyx.com/docs/account-setup/levels-and-capabilities/*` (Pretrial, Trial,
Paid, Verified) and `https://developers.telnyx.com/docs/account-setup/account-upgrade.md`.

Telnyx has two frameworks; the relevant one is PTPVE = Pretrial → Trial → Paid → Verified →
Enterprise.

**Trial account:** 1 verified number at a time (10 changes per account lifetime); 1 outbound
voice profile; outbound limited to dialling only the verified number; 2 concurrent outbound
calls; max 10 minutes per call; max 10 outbound calls/day; 1 API key; machine-generated voices
are prefixed with a mandatory Telnyx abuse disclaimer; **no access to Managed Accounts**; **no
access to Organizations and sub-users**; no access to Billing groups.

**Paid account:** "Limited set of outbound destination country codes"; **5 concurrent outbound
calls**; **max 100 outbound calls/day**; **max 10 outbound calls/hour**; number ordering limited
to the account's own country; **no access to Managed Accounts**; no DDoS mitigation.

**Verified account:** the voice limits above are lifted (the Verified page lists restrictions only
for number searching/ordering/porting, Managed Accounts, payment methods, and DDoS). **Still no
access to Managed Accounts.**

Criteria to reach Verified (from the account-upgrade table): verified email, passed fraud review,
verified mobile number, made a payment with CC/debit card, 2FA enabled, service address provided,
passed KYC, passed AI agent eval.

**Enterprise:** requires sales qualification. This is the level at which Managed Accounts become
available.

Separately, `https://developers.telnyx.com/docs/voice/sip-trunking/configuration/concurrent-limits.md`
publishes global outbound concurrency defaults: initial setup **2**, Level 2 verification
completed **10**, custom limit 10+ via support. Exceeding it returns
`403 User channel limit exceeded D1`.

### 5b. Caller ID: Telnyx does require verification, and it is enforced at the SIP layer

This is directly load-bearing for your "SDR's own verified number, we don't rent numbers" design.

- `https://developers.telnyx.com/docs/voice/troubleshooting/*` error tables publish:
  - `D51 | 403 | Non-Telnyx number not verified | Use Verified Numbers API`
  - `D36 | 403 | Using another account's DID as caller ID | Use only assigned phone numbers`
  - `D52-D54 | 403 | Restricted origination number`
  - `D60-D61 | 403 | Account tier requires verified numbers | Upgrade account tier or verify numbers`
  - `D35 | 403 | Invalid caller ID format | Use E.164 format`
  - `D7 / D38 | 403 | No outbound voice profile assigned to connection`
- The **Verified Numbers API** exists: `GET /v2/verified_numbers` (paginated),
  `https://developers.telnyx.com/api-reference/verified-numbers/list-all-verified-numbers`.
  API-creatable and API-listable.
- Caller ID policy, `https://developers.telnyx.com/docs/voice/sip-trunking/configuration/caller-id-policy.md`:
  - Caller ID is read from SIP headers in priority order: `P-Preferred-Identity`,
    `P-Asserted-Identity`, `Remote-Party-Id`, `FROM`.
  - Connections have a `outbound.localization` setting (e.g. `"ES"`), settable via
    `PATCH /v2/credential_connections/{id}` / `fqdn_connections` / `ip_connections`. When calling
    outside the localization country, only E.164 is accepted.
  - "Caller ID override" can be enabled per connection to bypass standard format validation.
  - **International spoofing restriction, verbatim:** *"Outbound calls to international
    destinations with spoofed caller IDs are rejected with a `503` error response."* Troubleshooting
    row: `503 | International spoofing | Use a valid origination number for the destination
    country`. For a Spain-CLI-to-Spain-destination motion this should be domestic, not
    international, but the precise definition of "spoofed" here is **NOT PUBLISHED** and interacts
    with the Verified Numbers mechanism in a way the docs do not spell out.
- STIR/SHAKEN attestation, `https://developers.telnyx.com/docs/voice/stir-shaken/attestation-behavior.md`:
  call from an owned number gets **A**; call from a **non-owned or verified number gets B**.
  (Relevant to US traffic reputation, not Spain, but note the model: your architecture
  structurally cannot get A-attestation.)

---

## 6. Multi-tenancy for an ISV — the three concepts, separated

These three are genuinely different mechanisms and are routinely conflated. Here they are
separated with citations.

### 6.1 Managed Accounts (Telnyx's name for sub-accounts)

**What it is:** a separate Telnyx account, owned by your account (the "manager account"), with
its **own organization**, its **own API credentials**, and optionally its **own balance**.

| Question | Answer | Citation |
|---|---|---|
| API-creatable? | **Yes.** `POST /v2/managed_accounts`, required body field `business_name`; optional `email`, `password`, `managed_account_allow_custom_pricing`, `rollup_billing`. Full CRUD plus enable/disable. | `https://developers.telnyx.com/api-reference/managed-accounts/create-a-new-managed-account` |
| Isolates billing? | **Configurable, and the choice is effectively permanent.** `rollup_billing` (boolean, default `false`): verbatim — *"Boolean value that indicates if the billing information and charges to the managed account 'roll up' to the manager account. If true, the managed account will not have its own balance and will use the shared balance with the manager account. This value cannot be changed after account creation without going through Telnyx support as changes require manual updates to the account ledger."* With `rollup_billing: false` the managed account has its own `balance` object (`balance`, `credit_limit`, `available_credit`, `currency`). | same |
| Isolates verified caller IDs? | **Yes, structurally** — the response includes its own `api_key`, `api_user`, `api_token`, and `organization`, and Verified Numbers is an account-scoped resource authenticated by Bearer key. **However this is an inference from resource scoping; there is NO document that states "verified numbers are isolated per managed account".** Treat as strongly implied, not published. | `.../create-a-new-managed-account` + `.../verified-numbers/list-all-verified-numbers` |
| Custom pricing per tenant? | **Yes.** `managed_account_allow_custom_pricing` (boolean, default `false`): verbatim — *"if the managed account is able to have custom pricing set for it or not. If false, uses the pricing of the manager account... there may be time lag between when the value is changed and pricing changes take effect."* | same |
| Capacity control per tenant? | **Yes.** `PATCH` endpoint: *"Update the amount of allocatable global outbound channels allocated to a specific managed account"*, plus *"Display information about allocatable global outbound channels for the current user. Only usable by account managers."* | `https://developers.telnyx.com/api-reference/managed-accounts/*` |
| Kill switch per tenant? | **Yes.** Disable: *"Disables a managed account, forbidding it to use Telnyx services, including sending or receiving phone calls and SMS messages."* Enable: *"Enables a managed account and its sub-users to use Telnyx services."* | same |

**THE BLOCKER — read this before modelling anything:** Managed Accounts are **gated behind
explicit Telnyx approval AND the Enterprise account level.**

- Both the list and create endpoint descriptions state verbatim: *"You need to be explictly
  approved by Telnyx in order to become a manager account."* (`sic`, Telnyx's typo)
- The account-level capability docs list **"ManagED Accounts — No access to APIs or features in
  this category"** at **Pretrial, Trial, Paid, AND Verified** levels. It is only available at
  Enterprise, and the Verified page states: *"Qualification by the Telnyx sales team is required
  to upgrade your account to the enterprise level to gain access to the above features."*
- Enterprise's published minimum commitment is **$5,000/mo** (`pricing.md`).

So the practical read: Telnyx's sub-account primitive is richer than Twilio's on paper
(per-tenant custom pricing, per-tenant channel allocation, per-tenant balance-or-rollup choice),
but it is **not self-serve** and appears to sit behind a $5,000/mo Enterprise commitment plus
sales qualification. Whether an approval can be obtained without the $5,000/mo commitment is
**NOT PUBLISHED** and can only come from sales.

### 6.2 Organization members / users

**What it is:** human logins inside **one** Telnyx account/organization. This is IAM, not
tenancy. It does not give you per-customer isolation.

| Question | Answer | Citation |
|---|---|---|
| API-creatable? | **No — read/delete only.** Published endpoints are `GET /v2/organizations/users` (list, with `filter[status]`, `filter[email]`, `include_groups`), `GET` one user (optionally including group memberships), `DELETE` a user (*"Removes the specified user from your organization"*), and a users-and-group-memberships report (*"returns all users without pagination"*). **There is no published POST/create endpoint.** Invitation appears to be a portal flow. | `https://developers.telnyx.com/api-reference/organization-users/*` |
| Isolates billing? | **No.** Verbatim from the account-levels overview: *"The level of an account is an organizational attribute. If the account is a paid account, all organization members have the privileges and limits of a paid account."* Members share the account's level, limits, and balance. | `https://developers.telnyx.com/docs/account-setup/levels-and-capabilities.md` |
| Isolates verified caller IDs? | **No.** Verified Numbers is scoped to the account/organization, not to the member. | inference from resource scoping; not separately documented |

Also note the account-level docs list "Organizations and sub-users" as **"No access"** at
Pretrial and Trial levels — so even the IAM layer is gated below Paid.

Conclusion: organization users are the wrong primitive for per-customer tenancy. They are for
your own staff, or possibly for a "one org per customer, you hold the keys" arrangement, which
gives you zero billing isolation.

### 6.3 Outbound Voice Profiles (OVPs)

**What it is:** a policy + rate + spend-control object attached to one or more connections,
**inside a single account**. This is the lightest-weight per-tenant primitive and it is fully
self-serve. Source:
`https://developers.telnyx.com/docs/voice/outbound-voice-profiles.md` (verbatim: *"The Telnyx
Outbound API allows you to create groups of settings and outbound profiles that allow you to
manage how outbound traffic is charged, managed and allowed or disallowed."*) and the API schema
at `https://developers.telnyx.com/api-reference/outbound-voice-profiles/create-an-outbound-voice-profile`.

| Question | Answer |
|---|---|
| API-creatable? | **Yes.** `POST /v2/outbound_voice_profiles`, only `name` is required (min length 3). |
| Isolates billing? | **Partially — cost attribution and spend caps, not separate balances or invoices.** Published fields: `billing_group_id` (uuid, *"The ID of the billing group associated with the outbound proflile"*, `sic`), `daily_spend_limit` (string USD, *"the maximum amount of usage charges, in USD, you want Telnyx to allow on this outbound voice profile in a day before disallowing new calls"*), `daily_spend_limit_enabled` (bool, default `false`), `usage_payment_method` (e.g. `rate-deck`). All charges still land on the one parent account balance and invoice. |
| Isolates verified caller IDs? | **No.** OVPs control *destinations*, not origination identity. `whitelisted_destinations` is an alpha-2 destination list (default `["US","CA"]` — you would need to add `ES`), `max_destination_rate` caps price-per-minute of an allowed destination. There is no caller-ID allowlist field on the OVP. The nearest thing is `call_recording.call_recording_type: by_caller_phone_number` + `call_recording_caller_phone_numbers[]`, which selects *which caller IDs get recorded* — a recording trigger, not an authorization boundary. |
| Other per-tenant controls | `concurrent_call_limit` (*"Must be no more than your global concurrent call limit. Null means no limit"*), `enabled` (*"Disabled profiles will result in outbound calls being blocked for the associated Connections"*), `traffic_type`, `service_plan` (e.g. `global`), `tags[]`, `connections_count`, and a BETA `calling_window` (`start_time`, `end_time`, `calls_per_cld`, all UTC) — the calling window is genuinely useful for Spanish SDR calling-hours compliance. |
| Gating | Available from Trial upward (Trial is limited to **1 OVP** at a time; Paid/Verified are not listed as OVP-limited). Also: `D7`/`D38` `403` if a connection has no OVP assigned. |

**A related object worth knowing:** **Billing Groups** — `POST /v2/billing_groups` (*"Create a
new billing group, which can be used to organize resources for billing purposes"*), full CRUD.
API-creatable. Referenced by `OutboundVoiceProfile.billing_group_id`. Also usable as a CDR usage
report aggregation dimension (`aggregation_type: BILLING_GROUP`). Note that Billing Groups are
listed as **"No access"** at Pretrial and Trial levels.

### 6.4 Summary of the three, side by side

| | Managed Account | Organization user | Outbound Voice Profile |
|---|---|---|---|
| Conceptually | a separate account/tenant | a human login | a traffic policy + spend cap |
| API-creatable | **Yes** (`POST /managed_accounts`) | **No** (GET/DELETE only) | **Yes** (`POST /outbound_voice_profiles`) |
| Separate API credentials | **Yes** (`api_key`, `api_user`, `api_token`) | No | No |
| Separate balance | **Optional** (`rollup_billing: false`) | No | No |
| Separate invoice | **Yes if `rollup_billing: false`** | No | No |
| Per-tenant cost attribution | Yes | No | Yes, via `billing_group_id` + CDR aggregation |
| Per-tenant spend cap | via allocated channels / own balance | No | **Yes** (`daily_spend_limit`) |
| Per-tenant concurrency cap | **Yes** (allocatable global outbound channels) | No | **Yes** (`concurrent_call_limit`) |
| Isolates verified caller IDs | Strongly implied by credential scoping, **not documented** | No | **No** |
| Per-tenant custom pricing | **Yes** (`managed_account_allow_custom_pricing`) | No | No |
| Self-serve | **NO** — Telnyx approval + Enterprise level | Paid+ | **Yes** (Trial+, 1 max on Trial) |

**Practical recommendation implied by the docs (not a Telnyx recommendation):** the only
self-serve per-tenant primitive is OVP + Billing Group. That gives you cost attribution, daily
spend caps, concurrency caps, destination allowlists, and calling windows per customer — but a
single balance, a single invoice, and a shared verified-caller-ID namespace. Real tenant
isolation requires Managed Accounts, which requires Enterprise + sales approval.

---

## 7. Per-customer cost attribution APIs

There are **three** distinct reporting surfaces. They are not interchangeable.

### 7.1 Usage Reports v2 — aggregated, near-real-time, supports managed accounts

`GET https://api.telnyx.com/v2/usage_reports`
Docs: `https://developers.telnyx.com/docs/reporting/usage-reports`
API ref: `https://developers.telnyx.com/api-reference/usage-reports-beta/get-telnyx-product-usage-data-beta`
(labelled **BETA** in the API reference)

- Verbatim purpose: *"a single endpoint that enables viewing aggregated usage data across all of
  a customer's Telnyx products... It can be used to efficiently monitor usage trends and costs,
  as well as to directly integrate with your internal systems."*
- **`managed_accounts` query parameter exists**, verbatim: *"Return the aggregations for all
  Managed Accounts under the user making the request."* (boolean). **This is the direct answer
  to your per-sub-account cost attribution question.**
- `cost` is a first-class **metric**; dimensions include `date`, `date_time` (hourly),
  `direction`, `country_code`, `currency`, `connection_id`, `short_duration_call`. Products
  include `sip-trunking`, `call-control` (Voice API), **`webrtc`**, `recording`,
  `media-storage`, `speech-to-text`, `call-control-features`, `conference`, `forking`,
  `media-streaming`, `cps`, `amd`, and more.
- Returns JSON by default; `format=csv` supported. Max date range **31 days**. Billing usage is
  calculated in UTC. Supports `date_range=last_N_days` literals.
- **Limitation, verbatim:** *"At this time, there is not a way to view usage for all or multiple
  products at once."* You must query per product.
- Supports `date_range=today` and an hourly `date_time` dimension, which is documentary evidence
  that data is available intra-day.

### 7.2 Detail Records Search — per-record, synchronous

`GET https://api.telnyx.com/v2/detail_records`
`https://developers.telnyx.com/api-reference/detail-records/search-detail-records`

- Verbatim: *"Search for any detail record across the Telnyx Platform."*
- `filter[record_type]` is **required**; enum includes `sip-trunking`, `call-control`,
  `recording`, `webrtc`, `media_storage`, `media-streaming`, `conference`, `stt`, `tts`,
  `noise-suppression`, `siprec-client`, `amd`, and others.
- `filter[date_range]` supports `today`, `yesterday`, `this_month`, `last_N_days`, etc.
- Record schemas expose **`cost`** (*"Amount, in the user currency, for the Telnyx billing
  cost"*), `billed_sec`, a billing-unit field, and `user_id`.
- **No `managed_accounts` filter is published on this endpoint.** So for per-tenant attribution
  via Detail Records you would query with each managed account's own API key (which
  `POST /managed_accounts` returns to you), rather than filtering centrally.

### 7.3 CDR Reports (batch/async) — explicitly managed-account aware

`https://developers.telnyx.com/api-reference/cdr-reports/*`

- `POST` a CDR report request, then poll. Published status enum: **`Pending = 1, Complete = 2,
  Failed = 3, Expired = 4`**. Completed reports expose a `report_url` (example in the spec:
  `http://portal.telnyx.com/downloads/report_name_8hvb45Gu.csv`).
- Request body includes **`managed_accounts`** (*"List of managed accounts to include"*, array of
  uuid) and **`select_all_managed_accounts`** (boolean). This is the cleanest published
  per-tenant CDR mechanism.
- `GET /cdr_reports/fields` (*"Get available CDR report fields"*) publishes a field group
  described as *"Cost and billing related information"* including **`cost`**.
- A related synchronous variant exists: `GET /reports/cdr_usage_reports/sync`, described verbatim
  as *"Generate and fetch voice usage report synchronously... No polling is necessary but the
  response may take up to a couple of minutes."* Aggregation types: `NO_AGGREGATION`,
  `CONNECTION`, `TAG`, **`BILLING_GROUP`**.

### 7.4 Real-time vs batch, and documented delay

| Surface | Real-time or batch | Documented delay |
|---|---|---|
| Usage Reports v2 (`/v2/usage_reports`) | Synchronous query, aggregated | **NOT PUBLISHED.** No stated freshness SLA or ingestion lag anywhere in the docs. Indirect evidence of intra-day availability: `date_range=today` is a supported value and `date_time` gives hourly granularity. |
| Detail Records (`/v2/detail_records`) | Synchronous, per-record | **NOT PUBLISHED.** `filter[date_range]=today` is supported. |
| CDR Reports (`POST` + poll) | **Batch/async** | Status enum `Pending/Complete/Failed/Expired` implies queueing; no published SLA on time-to-Complete. |
| `/reports/cdr_usage_reports/sync` | Synchronous but slow | **"may take up to a couple of minutes"** — the only quantified latency statement Telnyx publishes on any reporting surface. |
| Pricing API (`/v2/pricing/products/*`) | Synchronous | `pricing.md` states the pricing pages are *"cached for at most 24 hours"*; the endpoint itself advertises `Cache: s-maxage=300, stale-while-revalidate`. |

**Bottom line for your model:** there is a real per-sub-account cost attribution path
(`/v2/usage_reports?managed_accounts=true`, plus `managed_accounts[]` on CDR reports), but **no
published data-freshness guarantee**. If your product needs to show a customer their spend within
N minutes, that N is NOT PUBLISHED and must be established empirically or contractually.

Also relevant: `https://developers.telnyx.com/docs/account-setup/data-locality.md` publishes
selectable at-rest regions **US (default), EU (Germany), APAC (Australia), Middle East (UAE)**,
covering *"Call Detail Records (CDRs)... Media Storage (recordings)... Speech-to-Text"*. Useful
for a Spain/GDPR deployment.

There is also an **On-Demand Reports** feature that *"uses AI to translate natural language into
structured queries against your Usage Report data"*, with the published constraint: *"Queries run
against v2 Usage Report data only."*

Additional adjacent APIs: `GET /v2/invoices` (list, paginated, sortable) and
`GET /v2/invoices/{id}`.

---

## 8. Twilio equivalence check

Twilio's ISV pattern: one subaccount per customer + the Usage Records API.

**Verdict on the mechanics alone: Telnyx is materially BETTER. Verdict on access: Telnyx is
materially WORSE. Net verdict for a company not already at Enterprise scale: WORSE.**

Where Telnyx's model is better, per the docs:

1. Managed Accounts return their own `api_key`/`api_user`/`api_token` on creation, so tenant
   credential provisioning is a single API call.
2. `rollup_billing` gives an explicit choice between a shared balance and a per-tenant balance —
   a first-class, documented switch.
3. `managed_account_allow_custom_pricing` lets you set different rates per tenant. There is no
   equivalent in the Twilio pattern you described.
4. Per-tenant capacity governance is a documented endpoint (allocatable global outbound channels
   per managed account).
5. Attribution is available on two surfaces: `managed_accounts=true` on Usage Reports v2, and
   `managed_accounts[]` / `select_all_managed_accounts` on CDR reports.
6. OVPs give a *second*, lighter tenancy layer (daily spend limit, concurrency limit, destination
   allowlist, calling window) that works without Managed Accounts at all — you can ship
   multi-tenant-ish behaviour on a Paid/Verified account.
7. Data locality is selectable per region including EU (Germany).

Where Telnyx's model is worse, per the docs:

1. **Managed Accounts are not self-serve.** *"You need to be explictly approved by Telnyx in
   order to become a manager account."* Twilio subaccounts are self-serve from day one.
2. **Managed Accounts are listed as "No access" at Pretrial, Trial, Paid, and Verified levels.**
   Only Enterprise has them, and Enterprise's published minimum is **$5,000/mo** and requires
   sales qualification. That is a hard commercial gate on the entire ISV pattern.
3. **Organization users have no create endpoint** — only GET and DELETE. Programmatic user
   provisioning is not published.
4. Voice limits below Verified are severe for a dialer (Paid: 5 concurrent, 100 calls/day, 10
   calls/hour), so there is a verification ladder to climb before you can even load-test.
5. **No published freshness SLA on any reporting surface**, and the only quantified latency
   statement is "up to a couple of minutes" on a *synchronous* endpoint.
6. Telnyx adds two surcharges Twilio's published model does not have that bite this exact use
   case: **Short Duration Calls $0.01/call** once >15% of monthly traffic is ≤6 seconds (and it
   then applies retroactively to *all* SDCs that month), and **High Abandoned Call Rate
   $0.005/call**. Telnyx also states outright *"We do not support use cases that require Short
   Duration calls through our network."* An SDR power-dialer produces a lot of ≤6s calls.
7. T&C §21.9 publishes an automatic **8% per annum** escalator on all fees.

Equivalent, not better or worse: both round outbound to 60-second increments with a 60-second
minimum, so Telnyx offers **no relief on the short-call rounding penalty** you flagged for
Twilio.

---

## 9. Comparison table (Telnyx vs your researched Twilio figures)

Twilio column = the figures you supplied; I did not re-verify them. Telnyx column = read from a
Telnyx page or Telnyx public API today.

| Line item | Twilio (yours) | Telnyx | Telnyx status |
|---|---|---|---|
| Spain **mobile**, in-country (`local`) CLI | $0.0486/min (EEA origination) | **$0.028/min** | **PUBLISHED** — `telnyx.com/pricing/elastic-sip` (country = Spain, "Local - Mobile") and pricing API |
| Spain **landline**, in-country (`local`) CLI | $0.0178/min | **$0.012/min** | **PUBLISHED** — same two sources ("Local - Fixed") |
| Spain mobile, "From EEA" band | — | **$0.0211/min** generic; Telefonica $0.0284; Vodafone $0.0306; Xfera $0.0392 | **PUBLISHED** — pricing API only, not on the website |
| Spain landline, "From EEA" band | — | **$0.0118/min** | **PUBLISHED** — pricing API only |
| Spain mobile, non-EEA ("Non Surcharged") band | ~3.7x EEA rate | **$0.0221/min** generic; up to $0.0413 (Xfera) | **PUBLISHED** — pricing API only |
| Spain landline, non-EEA ("Non Surcharged") band | ~3.7x EEA rate | **$0.0123/min** | **PUBLISHED** — pricing API only |
| Spain landline, catch-all band (`origination_prefixes: null`) | — | **$0.4001/min** | **PUBLISHED** — pricing API only |
| **Which band applies to a `+34` SDR CLI dialling Spain** | n/a | Band A ($0.012 / $0.028) per Telnyx's own website rendering; Band B ($0.0118 / $0.0211) also matches on prefix `34` | **NOT PUBLISHED** — precedence rule undocumented. Resolve by test call + CDR `cost`, or written confirmation from Telnyx sales/support. |
| Effective Spanish mobile blend across carriers | single blended rate | depends on MNP carrier mix of your list | **NOT PUBLISHED** — must come from your own CDRs |
| Billing increment | rounds up to next minute | **60s first increment, 60s subsequent** (`interval_1: 60, interval_n: 60` on all 2,428 outbound rows, all 34 Spain rows) | **PUBLISHED** — pricing API; T&C §12.1 states 60/60 for US/Canada only |
| Browser / WebRTC leg | $0.0040/min | **$0.002/min** | **PUBLISHED** — `telnyx.com/pricing/call-control` ("Browser/app calling") + `developers.telnyx.com/docs/voice/webrtc/sdk-commonalities` |
| Voice API / Call Control platform fee per PSTN leg | n/a | **$0.002/min** each direction | **PUBLISHED** — `pricing/call-control` + `voice-api` pricing API |
| Whether the browser leg also incurs a Call Control leg fee | n/a | — | **NOT PUBLISHED** — resolve by test call + CDR |
| SIP-to-SIP / on-net free tier | n/a | no free tier published; SIP interface $0.002/min, SIP URI origination $0.002/min, SIP subdomain $0.002/min | **NOT PUBLISHED** (as free); the charges are PUBLISHED |
| Call recording | $0.0025/min | **$0.002/min** | **PUBLISHED** — both Telnyx voice pricing pages |
| Recording storage | $0.0005/min/month, first 10,000 min free | **$0 per minute** | **PUBLISHED** — both pages, verbatim "Call recording storage — $0 per minute"; pricing API `voice-api` = $0.0/min |
| Recording storage retention window | n/a | — | **NOT PUBLISHED** — support or Service Order |
| Whether recording a bridged 2-leg call bills once or twice | n/a | two separate $0.002/min line items exist (origination-leg, termination-leg) | **NOT PUBLISHED** — resolve by test call + CDR |
| Dual-channel recording surcharge | n/a | none published; `call_recording_channels: dual` is a config value on the OVP | **PUBLISHED** (as a capability); no surcharge published |
| Cloud Storage per GB (only if exporting off Telnyx) | n/a | `/pricing/storage` says $0.012/GB; pricing API says $0.0/GB default, $0.025/GB EU, $0.025/GB APAC; `/pricing/call-control` cross-link says "starting at $0.006 per GB" | **CONFLICTING PUBLISHED VALUES** — do not use; confirm with Telnyx |
| Short Duration Call surcharge (≤6s, >15% of monthly traffic) | not in your figures | **$0.01 per call**, applied retroactively to all SDCs that month | **PUBLISHED** — T&C §12.1 + support article 1130707 + `sip-trunking` pricing API |
| High Abandoned Call Rate surcharge | not in your figures | **$0.005 per abandoned call** | **PUBLISHED** — `sip-trunking` pricing API |
| CPS peak surcharge | n/a | graduated $12–$30/CPS above 5 free CPS, **but Programmable Voice / Call Control traffic is excluded** | **PUBLISHED** — support article 7834487 |
| Monthly minimum (PAYG) | n/a | **$0/mo** | **PUBLISHED** — `telnyx.com/pricing.md` |
| Platform fee for voice/WebRTC | n/a | none published | **PUBLISHED** (absence: PAYG stated as $0/mo, no fee line item on either voice page) |
| Committed plan minimum | n/a | **$500/mo** | **PUBLISHED** — `pricing.md` |
| Enterprise minimum | n/a | **$5,000/mo** | **PUBLISHED** — `pricing.md` |
| Volume discount rate card | n/a | — | **NOT PUBLISHED** — sales quote only |
| Trial credit | n/a | **$5** (Trial); **$25 in AI credits** (Pretrial) | **PUBLISHED** — account-level docs |
| Annual price escalator | n/a | **8% per annum**, automatic | **PUBLISHED** — T&C §21.9 |
| Sub-account primitive | subaccount, self-serve | **Managed Account**, `POST /v2/managed_accounts` | **PUBLISHED** — but requires explicit Telnyx approval and Enterprise level |
| Sub-account self-serve? | yes | **no** | **PUBLISHED** — "No access" at Pretrial/Trial/Paid/Verified |
| Per-tenant usage + cost API | Usage Records API | `/v2/usage_reports?managed_accounts=true` (BETA); CDR reports `managed_accounts[]` | **PUBLISHED** |
| Reporting freshness SLA | n/a | — | **NOT PUBLISHED**; only `/reports/cdr_usage_reports/sync` "up to a couple of minutes" is quantified |
| Verified caller ID mechanism | Verified Caller IDs | **Verified Numbers API** (`GET /v2/verified_numbers`); unverified non-Telnyx CLI rejected `403 D51` | **PUBLISHED** |
| Per-tenant verified-caller-ID isolation | subaccount-scoped | strongly implied by managed-account credential scoping | **NOT PUBLISHED** as an explicit statement |
| EU data residency | n/a | EU (Germany) selectable; covers CDRs, recordings, STT | **PUBLISHED** — data-locality doc |

---

## 10. Open items that require a human (ranked by financial impact)

1. **Band precedence for a `+34` CLI into Spain.** Worth 33x on landline ($0.012 vs $0.4001) and
   ~1.3x on mobile. Resolve by: test call from a verified `+34` number to a Spanish landline and a
   Spanish mobile, then read `cost` and `billed_sec` from `/v2/detail_records?filter[record_type]=sip-trunking`.
2. **Whether Managed Accounts can be approved without a $5,000/mo Enterprise commitment.** This
   determines whether the whole ISV architecture is viable on Telnyx. Sales question only.
3. **Short Duration Call exposure.** Model your expected % of ≤6s calls. If >15%, add $0.01 to
   *every* SDC that month, and note Telnyx's written position that it does not support the use
   case. Get written confirmation before committing.
4. **Whether a bridged click-to-call bills the Call Control leg fee once or twice, and whether
   recording bills once or twice.** Worth $0.002–$0.004/min. Test call + CDR.
5. **Recording storage retention window** behind the $0/min figure.
6. **Reporting freshness** if you surface live spend to customers.
7. **Volume discount rate card** for Spain specifically, once you have a volume forecast.
8. **Cloud Storage per-GB rate for the EU region** — three conflicting published numbers.

---

## Sources

All URLs fetched or queried 2026-08-27.

**Telnyx pricing pages**
- https://telnyx.com/pricing/call-control — Voice API pay-as-you-go; browser/app calling; call recording; call recording storage; SIP interface; STT/TTS; local-cost-rate FAQ
- https://telnyx.com/pricing/elastic-sip — SIP Trunking pay-as-you-go; **country selector set to Spain** yielded "Local - Fixed $0.012 per minute" and "Local - Mobile $0.028 per minute"; inbound Spain; channel pricing; links to the CPS surcharge article
- https://telnyx.com/pricing/storage — $0.012 per GB
- https://telnyx.com/pricing.md — canonical machine-readable pricing; Plans (PAYG $0 / Committed $500 / Enterprise $5,000); Rate Limits; the statement that `/pricing/*` pages render from `api.telnyx.com/v2/pricing/products/{slug}`; the statement that `elastic-sip-outbound` is deliberately not listed there

**Telnyx public pricing API (unauthenticated)**
- https://api.telnyx.com/v2/pricing/products/elastic-sip-outbound — 2,428 rows; `?filter[country_iso]=ES` → 34 Spain rows across four `origination_prefixes` bands; all rows `interval_1: 60, interval_n: 60`
- https://api.telnyx.com/v2/pricing/products/voice-api — 83 rows; Call Control origination/termination $0.002/min; recording origination/termination $0.002/min; recording storage $0.0/min; SIPREC $0.002/min; forking $0.0025/min; media streaming over WebSocket $0.0035/min
- https://api.telnyx.com/v2/pricing/products/sip-trunking — 29 rows; SDC surcharge $0.01/call; abandoned-call surcharge $0.005/call; CPS peak surcharge $0.0; channel MRC tiers and zones; SIP URI origination $0.002/min; SIP subdomain $0.002/min
- https://api.telnyx.com/v2/pricing/products/storage — $0.0/GB/mo default region, $0.025/GB/mo EU, $0.025/GB/mo APAC; media storage $0.0/event
- https://api.telnyx.com/v2/pricing/products/account-services — BAA $2,500/mo; support services minimum commitment $10,000/mo
- https://api.telnyx.com/v2/pricing/products/global-numbers — Spain Local number MRC $1.00, OTC $1.00; Mobile MRC $1.50, OTC $3.00 (not needed for this use case; recorded for completeness)
- https://api.telnyx.com/v2/pricing/products/inbound-voice — Spain Inbound Local from Landline/Mobile $0.008/min; Inbound National $0.0032/min

**Telnyx docs**
- https://developers.telnyx.com/llms.txt — documentation index; pointer to `pricing.md`
- https://developers.telnyx.com/docs/development/llms/fundamentals-llms-full-txt — consolidated Fundamentals corpus (464 KB): account levels, Usage Reports guide, API reference index
- https://developers.telnyx.com/docs/development/llms/calling-llms-full-txt — consolidated Calling corpus (1.09 MB): WebRTC costs, caller ID policy, concurrent limits, SIP error codes, STIR/SHAKEN attestation
- https://developers.telnyx.com/docs/voice/webrtc/sdk-commonalities.md — "Costs: WebRTC call legs are billed at $0.002/minute."
- https://developers.telnyx.com/docs/voice/sip-trunking/configuration/caller-id-policy.md — SIP header priority, localization, international spoofing 503
- https://developers.telnyx.com/docs/voice/sip-trunking/configuration/concurrent-limits.md — default concurrency 2 / 10 / 10+
- https://developers.telnyx.com/docs/voice/stir-shaken/attestation-behavior.md — owned number = A, non-owned or verified = B
- https://developers.telnyx.com/docs/account-setup/levels-and-capabilities.md — PTPVE framework; org members inherit account level
- https://developers.telnyx.com/docs/account-setup/levels-and-capabilities/pretrial.md — $25 AI credits
- https://developers.telnyx.com/docs/account-setup/levels-and-capabilities/trial.md — $5 testing credit; 1 verified number; 1 OVP; 2 concurrent; 10 calls/day
- https://developers.telnyx.com/docs/account-setup/levels-and-capabilities/paid.md — 5 concurrent; 100 calls/day; 10 calls/hour; Managed Accounts no access
- https://developers.telnyx.com/docs/account-setup/levels-and-capabilities/verified.md — Managed Accounts no access; Enterprise requires sales qualification
- https://developers.telnyx.com/docs/account-setup/account-upgrade.md — upgrade criteria matrix
- https://developers.telnyx.com/docs/account-setup/data-locality.md — US/EU(Germany)/APAC/Middle East; covers CDRs, recordings, STT
- https://developers.telnyx.com/docs/reporting/usage-reports — Usage Reports v2 guide; product list; 31-day max range; `cost` metric; short-duration-call dimension
- https://developers.telnyx.com/docs/voice/outbound-voice-profiles.md — OVP overview

**Telnyx API reference**
- https://developers.telnyx.com/api-reference/managed-accounts/create-a-new-managed-account — `rollup_billing`, `managed_account_allow_custom_pricing`, returned `api_key`/`api_user`/`api_token`, `balance`; "explictly approved by Telnyx"
- https://developers.telnyx.com/api-reference/managed-accounts/lists-accounts-managed-by-the-current-user — same approval requirement
- https://developers.telnyx.com/api-reference/managed-accounts/update-the-amount-of-allocatable-global-outbound-channels-allocated-to-a-specific-managed-account
- https://developers.telnyx.com/api-reference/managed-accounts/disables-a-managed-account and .../enables-a-managed-account
- https://developers.telnyx.com/api-reference/organization-users/list-organization-users — GET only; no create endpoint published
- https://developers.telnyx.com/api-reference/outbound-voice-profiles/create-an-outbound-voice-profile — `daily_spend_limit`, `billing_group_id`, `whitelisted_destinations`, `max_destination_rate`, `concurrent_call_limit`, `call_recording.call_recording_channels: dual`, BETA `calling_window`
- https://developers.telnyx.com/api-reference/detail-records/search-detail-records — `filter[record_type]` enum; `cost`, `billed_sec`; no managed-account filter
- https://developers.telnyx.com/api-reference/cdr-reports/create-a-new-cdr-report-request — `managed_accounts[]`, `select_all_managed_accounts`; status Pending/Complete/Failed/Expired
- https://developers.telnyx.com/api-reference/cdr-reports/get-available-cdr-report-fields — "Cost and billing related information" incl. `cost`
- https://developers.telnyx.com/api-reference/cdr-usage-reports/generates-and-fetches-cdr-usage-reports — "may take up to a couple of minutes"; aggregation by `BILLING_GROUP`
- https://developers.telnyx.com/api-reference/usage-reports-beta/get-telnyx-product-usage-data-beta — `managed_accounts` boolean param, "Return the aggregations for all Managed Accounts under the user making the request"
- https://developers.telnyx.com/api-reference/verified-numbers/list-all-verified-numbers — `GET /v2/verified_numbers`
- https://developers.telnyx.com/api-reference/billing-groups/create-a-billing-group

**Telnyx legal / support**
- https://telnyx.com/terms-and-conditions-of-service — §12.1 sixty-second increments (US/Canada), Short Duration definition and $0.01/call surcharge; §21.9 8% per annum escalator
- https://support.telnyx.com/en/articles/1130707-what-are-short-duration-calls — ≤6s definition, 15% threshold, retroactive application, international since 2024-01-01, "We do not support use cases that require Short Duration calls"
- https://support.telnyx.com/en/articles/7834487-calls-per-second-cps-surcharges — 20 CPS default real-time limit; graduated monthly 95th-percentile peak CPS surcharge; Programmable Voice / Call Control excluded

**Not used as a Telnyx source (third-party, listed only for transparency)**
- A court-filed exhibit of an older Telnyx MSA surfaced in search and corroborated §12.1's
  sixty-second-increment language. I did not rely on it; the live T&C page says the same thing.
