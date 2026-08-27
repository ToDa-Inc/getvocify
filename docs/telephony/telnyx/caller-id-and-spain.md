# Telnyx: caller ID / verified numbers / Spain

Research scope: Telnyx caller ID / external-number (Verified Numbers) policy and Spanish
regulatory requirements, for outbound click-to-call where the CLI is the SDR's own
pre-existing +34 number (not purchased from the carrier).

All dates accessed: **2026-08-27**.

Every claim below is tagged **DOCUMENTED** (with the URL it came from) or **NOT DOCUMENTED**.
Nothing in this document is inferred from a search-engine summary; where a search engine
asserted something that the underlying page did not say, that is called out in the
"Contradictions or ambiguities" section.

---

## Sources fetched

| URL | What it covers | Accessed |
| --- | --- | --- |
| https://support.telnyx.com/en/articles/6790265-verified-numbers-faq | Verified Numbers FAQ: definition, channels, pricing, bulk KYC, org/sub-user sharing | 2026-08-27 |
| https://support.telnyx.com/en/articles/6988813-verified-numbers | Verified Numbers main article: portal steps, DTMF, API, webhooks, D51 rejection, SIP header priority, pricing | 2026-08-27 |
| https://support.telnyx.com/en/articles/13854980-beta-how-to-verify-phone-numbers-using-dtmf-press-1-to-verify | BETA "Press 1 to verify" DTMF flow, bulk loop examples, troubleshooting | 2026-08-27 |
| https://developers.telnyx.com/api-reference/verified-numbers/request-phone-number-verification | OpenAPI for `POST /v2/verified_numbers` incl. `verification_method` enum and `extension` | 2026-08-27 |
| https://developers.telnyx.com/api-reference/verified-numbers/list-all-verified-numbers | OpenAPI for `GET /v2/verified_numbers`, response schema (`phone_number`, `record_type`, `verified_at`) | 2026-08-27 |
| https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json | Consolidated Telnyx OpenAPI 3.1 spec — full Verified Numbers path/verb/schema surface | 2026-08-27 |
| https://support.telnyx.com/en/articles/3546251-caller-id-number-policy | Caller ID Number Policy: formats, localisation, SIP header priority, `Privacy: id`, EEA PAI warning, international spoofing | 2026-08-27 |
| https://developers.telnyx.com/docs/voice/sip-trunking/configuration/caller-id-policy.md | Developer-docs version of caller ID policy incl. 403 D35 / 404 / 503 table and Caller ID Override | 2026-08-27 |
| https://support.telnyx.com/en/articles/6247033-cli-cld-validation-faq | CLI/CLD numbering-database validation — scope is NANPA only | 2026-08-27 |
| https://support.telnyx.com/en/articles/4409457-telnyx-sip-response-codes | SIP cause codes D34, D35, D36, D51, D54, D58, D60 | 2026-08-27 |
| https://support.telnyx.com/en/articles/1311073-spain-did-requirements | Spain DID KYC: DNI/NIE, CIF, company registration, address matching area code, proof of address, physical presence | 2026-08-27 |
| https://telnyx.com/phone-numbers/spain | Telnyx's own statement on Order TDF/149/2025, Lista Robinson, LSSI Art. 21, fines; Spain area codes | 2026-08-27 |
| https://telnyx.com/acceptable-use-policy | Full AUP text: CLI misuse clause, auto/predictive dialing, unsolicited calls, ASR, abandoned calls, live-human-dialog clause | 2026-08-27 |
| https://support.telnyx.com/en/articles/1189141-get-started-with-organizations | Organizations / sub-users: permissions, ownership limits, invite limits, V2 caveat | 2026-08-27 |
| https://support.telnyx.com/en/articles/4951492-managed-accounts | Managed Accounts: independent orgs, own balance/API keys, MSP use case (via search extract) | 2026-08-27 |
| https://telnyx.com/release-notes/managed-accounts | Managed Accounts release note: manager account, inherited pricing, API control (via search extract) | 2026-08-27 |
| https://developers.telnyx.com/docs/account-setup/levels-and-capabilities/trial | Trial-account limits incl. explicit Verified Numbers caps | 2026-08-27 |
| https://developers.telnyx.com/docs/account-setup/levels-and-capabilities/verified | Verified (L2) account privileges/limitations — what stays restricted | 2026-08-27 |
| https://support.telnyx.com/en/articles/1130595-account-verification | Account levels: L1 vs L2, L2 needed for international numbers/calling (via search extract) | 2026-08-27 |
| https://developers.telnyx.com/docs/voice/programmable-voice/l1-accounts-restirctions.md | L1 Programmable Voice restrictions (100 calls/day, 10/hour, forced disclaimer) | 2026-08-27 |
| https://developers.telnyx.com/docs/development/api-fundamentals/reliability/rate-limiting.md | Generic REST rate-limit model; explicitly says do not infer one product's limits for another | 2026-08-27 |
| https://developers.telnyx.com/docs/voice/sip-trunking/configuration/outbound-voice-profiles | Outbound Voice Profiles: allowed destinations, channel limits, spend limits (via search extract) | 2026-08-27 |
| https://developers.telnyx.com/docs/identity/verify/security-best-practices | Verify (2FA) product rate-limit recommendations — a DIFFERENT product, included to prevent conflation | 2026-08-27 |
| https://developers.telnyx.com/api-reference/verify/update-verify-profile | Verify (2FA) `whitelisted_destinations` field — DIFFERENT product, included to prevent conflation | 2026-08-27 |
| https://developers.telnyx.com/llms.txt + section indexes (`calling-llms-txt`, `numbers-identity-llms-txt`) | Full developer-docs page inventory; used to establish Verified Numbers has NO narrative dev-docs page | 2026-08-27 |
| https://telnyx.com/global-coverage | Coverage claims: 130+ countries local calling, 230+ intl SIP trunking, licenses in 30+ countries | 2026-08-27 |
| https://telnyx.com/release-notes/telnyx-verified-numbers | Feature launch note (15 Feb 2023): portal or REST API, SMS or voice | 2026-08-27 |

---

## Findings

### Q2 (answered first — the gating question). Country coverage of Verified Numbers

**DOCUMENTED — the API imposes no country constraint in its schema.**
The request body for `POST /v2/verified_numbers` has exactly three properties:
`phone_number` (`type: string`, example `+15551234567`), `verification_method`
(`enum: [sms, call]`), and `extension`. There is **no** country field, no country
allow-list, no country-scoped error, and no ISO-3166 parameter anywhere in the Verified
Numbers surface. Source:
https://developers.telnyx.com/api-reference/verified-numbers/request-phone-number-verification
and confirmed against the consolidated spec
(https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json), where the
complete Verified Numbers surface is only:
`GET|POST /verified_numbers`, `GET|DELETE /verified_numbers/{phone_number}`,
`POST /verified_numbers/{phone_number}/actions/verify`.

**DOCUMENTED — the response schema is country-agnostic.** `VerifiedNumberResponse` contains
only `phone_number`, `record_type` (`verified_number`), and `verified_at`. Source:
https://developers.telnyx.com/api-reference/verified-numbers/list-all-verified-numbers

**DOCUMENTED — Telnyx's own framing of the feature is provider-agnostic, not country-scoped.**
"A Verified Number has not been obtained through Telnyx but instead obtained through a
different provider… the customer wants to use that number as a CLI for outbound calls made
through Telnyx." No geography is mentioned anywhere in the FAQ. Source:
https://support.telnyx.com/en/articles/6790265-verified-numbers-faq

**NOT DOCUMENTED — whether a Spanish +34 mobile can be verified.** No Telnyx page states
that +34 mobiles are supported, and none states they are excluded.

**NOT DOCUMENTED — whether a Spanish +34 geographic landline (91x / 93x) can be verified.**
This is the higher-risk case of the two, because verification is delivered by SMS or by an
automated voice call. A geographic landline cannot receive SMS, so it would depend entirely
on the `call` (IVR reads the code twice) or `dtmf` (press 1) methods reaching a +34 fixed
line. Telnyx documents that both call-based methods exist
(https://support.telnyx.com/en/articles/6988813-verified-numbers) but documents nothing about
their country reach.

**NOT DOCUMENTED — any supported/unsupported country list for Verified Numbers.** I checked
the full developer-docs inventory (https://developers.telnyx.com/llms.txt and the `Calling`
and `Numbers → Identity` section indexes). Verified Numbers appears **only** as API-reference
endpoints; it has **no narrative documentation page at all** on developers.telnyx.com. The
only prose lives in the three support-centre articles. None of them mention countries.

**Important non-conflation warning.** The Telnyx *Verify* API (2FA / OTP-for-your-end-users)
is a **separate product** and it *does* have a documented country control:
`whitelisted_destinations` accepting ISO 3166-1 alpha-2 codes
(https://developers.telnyx.com/api-reference/verify/update-verify-profile). Verified Numbers
(caller-ID authorisation) has no such field. Do not read the Verify product's country
controls as evidence about Verified Numbers coverage — they are different APIs under
different docs trees.

**Bottom line on Q2:** Telnyx does **not** document a US-only or North-America-only
restriction on Verified Numbers (unlike the reported Twilio behaviour), but it also does
**not** document positive Spain support. The docs are simply silent. **This must be tested or
confirmed by Telnyx in writing before Telnyx can be treated as viable.**

*To resolve:* (a) on a Level-2 account, call `POST /v2/verified_numbers` with a real +34 6xx
mobile via `sms`, and separately with a real +34 91x/93x landline via `call` and via `dtmf`,
and record whether the request 200s, whether delivery actually occurs, and whether
`POST /verified_numbers/{n}/actions/verify` accepts the code; (b) ask Telnyx support/sales in
writing for the Verified Numbers country coverage matrix, explicitly naming ES mobile and ES
geographic fixed.

---

### Q1. Verified Numbers mechanics

**DOCUMENTED — what it is.** A number not ported to Telnyx, whose owner has authenticated
ownership, so it may be used as CLI for outbound calls through Telnyx. The number keeps
receiving inbound calls and messages through the original external provider. Applies to
**voice services only** (SIP Trunking and Programmable Voice), not SMS. Source:
https://support.telnyx.com/en/articles/6790265-verified-numbers-faq

**DOCUMENTED — delivery channels.**
- `sms` — a validation code is sent by SMS.
- `call` — a voice call is placed and an IVR **plays the validation code twice**.
- `dtmf` — an automated call where the recipient **presses 1**, no code; marked **BETA**.
  Telnyx notes "the verification call does not mention Telnyx anywhere, maintaining privacy."
- `extension` — optional DTMF sequence (digits `0-9`, `A-D`, `*`, `#`, `w`=0.5s pause,
  `W`=1s pause, max 50 chars) dialled after answer, for numbers behind an IVR. `call` only.

Sources: https://support.telnyx.com/en/articles/6988813-verified-numbers,
https://support.telnyx.com/en/articles/13854980-beta-how-to-verify-phone-numbers-using-dtmf-press-1-to-verify,
https://developers.telnyx.com/api-reference/verified-numbers/request-phone-number-verification

**DOCUMENTED — there is a public REST API. It is NOT portal-only.** Exact paths, base
`https://api.telnyx.com/v2`, bearer auth:

| Method | Path | Operation |
| --- | --- | --- |
| `POST` | `/v2/verified_numbers` | `CreateVerifiedNumber` — initiate verification. Required: `phone_number`, `verification_method`. Optional: `extension`, `verification_webhook_url`. |
| `POST` | `/v2/verified_numbers/{phone_number}/actions/verify` | `VerifyVerificationCode` — submit the code. Required body: `verification_code`. |
| `GET` | `/v2/verified_numbers` | `ListVerifiedNumbers` — paginated (`page[size]` default 25, `page[number]` default 1). |
| `GET` | `/v2/verified_numbers/{phone_number}` | `GetVerifiedNumber` — retrieve one. |
| `DELETE` | `/v2/verified_numbers/{phone_number}` | `DeleteVerifiedNumber` — remove a verified number. |

Sources: consolidated OpenAPI spec (spec3.json, paths enumerated directly) and
https://developers.telnyx.com/api-reference/verified-numbers/request-phone-number-verification

**DOCUMENTED — webhooks instead of polling.** Pass `verification_webhook_url` in the POST
body; Telnyx pushes `event_type: "caller_id_verification.completed"` with payload
`{phone_number, record_type: "caller_id_verification", verification_method:
"outbound_call", verified_at}`. Sources: the Verified Numbers article and the DTMF BETA
article (URLs above).

**DOCUMENTED — portal path.** Mission Control Portal → Voice Suite → "Verified Numbers"
(the DTMF article gives the path as Numbers → Verify Numbers), add number, choose SMS / Call
/ "Press 1 to verify", enter the code, press "Verify Number". Source:
https://support.telnyx.com/en/articles/6988813-verified-numbers

**DOCUMENTED — cost.** $0.03 per **successful** verification, plus the underlying
SMS/Voice/Flash channel charge for the destination. Sources: both Verified Numbers articles.

**DOCUMENTED — bulk path above 200 numbers.** "If you have over 200 non-Telnyx [numbers] on
calls through the Telnyx platform, we will assist you through a bulk verification process.
This process will be a reinforced KYC process that will [be] carried out with the help of
your account manager." Source:
https://support.telnyx.com/en/articles/6790265-verified-numbers-faq

**NOT DOCUMENTED — the code length, the code TTL / how long a pending verification stays
valid, and whether a pending verification can be cancelled or re-triggered for the same
number.** (Code length and a 300s default timeout are documented for the *Verify* 2FA
product, not for Verified Numbers — do not carry that across.)

**NOT DOCUMENTED — what identity/KYC evidence, if any, is required for a normal
(sub-200) verification beyond possession of the number.**

---

### Q3. Limits

**DOCUMENTED — trial accounts.** Verified numbers on a trial account are limited to
**1 verified number at any one time**, **10 changes per trial account lifetime**, and
**15 delivery attempts per trial account lifetime regardless of conversion outcome**.
Source: https://developers.telnyx.com/docs/account-setup/levels-and-capabilities/trial

**DOCUMENTED — Verified (Level 2) accounts have no stated Verified Numbers cap.** The
"Verified Account Privileges & Limitations" page enumerates what remains restricted after
verification (number blocks, LRN migration, Managed Accounts, DDoS mitigation) and does
**not** list any Verified Numbers limit; it states "Full access except otherwise specified
below" and "Telnyx reserves the right to modify limitations without notification". Source:
https://developers.telnyx.com/docs/account-setup/levels-and-capabilities/verified

**DOCUMENTED — >200 non-Telnyx numbers triggers a reinforced-KYC bulk process with an
account manager** (see Q1). This is the only volume threshold Telnyx publishes for this
feature. Source: https://support.telnyx.com/en/articles/6790265-verified-numbers-faq

**DOCUMENTED — related L1 voice ceilings that would throttle a pilot.** L1-verified accounts:
max 100 outbound calls/day, 10 outbound calls/hour, and all machine-generated speak commands
are prefixed with a Telnyx abuse disclaimer. Source:
https://developers.telnyx.com/docs/voice/programmable-voice/l1-accounts-restirctions.md

**NOT DOCUMENTED — maximum number of verified numbers per non-trial account.**

**NOT DOCUMENTED — maximum number of verified numbers per sub-user.**

**NOT DOCUMENTED — expiry / re-verification.** The stored record exposes `verified_at` and
there is **no** `expires_at`, `status`, or `revalidate_at` field in the schema
(https://developers.telnyx.com/api-reference/verified-numbers/list-all-verified-numbers).
No article states that verifications expire, and none states that they are permanent. There
is a `DELETE` endpoint, so removal is explicit, but nothing documents automatic expiry.

**NOT DOCUMENTED — numeric rate limits on verification attempts.** The DTMF BETA article says
only "Add delays between bulk verification requests to avoid rate limiting", uses
`time.sleep(1)` / `sleep 1` in its examples, and lists "Rate limit exceeded" as a
troubleshooting item — but publishes **no numbers**. Source:
https://support.telnyx.com/en/articles/13854980-beta-how-to-verify-phone-numbers-using-dtmf-press-1-to-verify
The generic API rate-limiting page confirms limits vary by endpoint, are conveyed via
`x-ratelimit-*` / `retry-after` headers, return `429` with error code `10011`, and explicitly
warns "Do not infer Messaging limits for Voice, Storage, Wireless, or other APIs" and "A
missing header is not evidence that an endpoint has no limit". Source:
https://developers.telnyx.com/docs/development/api-fundamentals/reliability/rate-limiting.md

> **Do not use** the table at
> https://developers.telnyx.com/docs/identity/verify/security-best-practices
> (3 attempts/10 min per number, 5/hour per number, 10/hour per IP, 5/hour per account) as
> Telnyx's Verified Numbers limits. That page belongs to the **Verify 2FA product** and is
> written as *recommendations for the customer to implement*, not as Telnyx-enforced limits.

*To resolve:* read `x-ratelimit-limit` / `x-ratelimit-remaining` / `retry-after` off live
`POST /v2/verified_numbers` responses, and ask Telnyx for the per-account verified-number cap
and whether verifications are permanent.

---

### Q4. Sub-user / organization semantics

**DOCUMENTED — the FAQ claim, verbatim.** "If the owner of the account adds a verified
number, the number is available to be used by all users. If a sub-user adds a verified
number, the number should be available exclusively for that particular user only. Therefore,
if you want to share the verified numbers across the organization, please ask the account
admin user to verify the number." Source:
https://support.telnyx.com/en/articles/6790265-verified-numbers-faq

Note the hedged verb "**should be**", not "is". This is the only statement Telnyx publishes
on the subject.

**DOCUMENTED — which Telnyx concept "sub-user" refers to.** Telnyx uses "sub-accounts, also
known as sub-members or sub-users" for members of a **User Organization**: multiple user
accounts tied into one umbrella entity headed by a single organization owner, governed by
group-level permissions. Source:
https://support.telnyx.com/en/articles/1189141-get-started-with-organizations
The FAQ's "sub-user" therefore maps to **organization sub-members**, not to Managed Accounts.

**DOCUMENTED — Organizations are explicitly the wrong primitive for multi-tenant SaaS.** From
the same page:
- "user organizations are allowed only one net running balance and payment method — **it is
  not meant to be a system for re-sellers to allow their customers access to their Telnyx
  account directly. Please check out our managed accounts feature instead.**"
- "A sub-account **cannot 'own' most things in the system**, such as numbers, connections,
  outbound profiles, etc. Instead sub-accounts interact with things owned by the organization
  owner."
- "not all our new V2 services are exposed to the organizations functionality… **we strongly
  recommend that sub members leverage the API key of their organization owners account.**"
- Invites: max **10 per hour**, max **10 open at any time**, resend max 5 times / every 5 min.
- "**A user, that you want to send an invite to join your organization, must not be signed up
  with Telnyx already**"; existing Telnyx users must email support to have their account
  cancelled first.
- "You can only create **one organization per account**."

**DOCUMENTED — Managed Accounts are a different concept.** "Each Managed Account is its own
**independent Telnyx organization** with its own balance, API keys, usage, and settings",
created from a **manager account**, aimed at MSPs managing customer accounts; manager
accounts can create API keys scoped to a Managed Account and drive them via the API; pricing
is inherited and hidden from the Managed Account. Sources:
https://support.telnyx.com/en/articles/4951492-managed-accounts and
https://telnyx.com/release-notes/managed-accounts

**DOCUMENTED — Managed Accounts are gated.** Manager accounts must be created **manually by
Telnyx sales**, the feature was introduced as a **limited release** for "qualifying users",
and the Verified (L2) account page lists "ManagED Accounts — No access to APIs or features in
this category", requiring "Qualification by the Telnyx sales team… to upgrade your account to
the enterprise level". Sources:
https://developers.telnyx.com/docs/account-setup/levels-and-capabilities/verified,
https://support.telnyx.com/en/articles/4951492-managed-accounts,
https://telnyx.com/resources/managed-account

**What this means for Vocify, stated only as far as the docs support it.**
The Organizations route is documented as unsuitable: each SDR would need a full Telnyx user
account that has never existed on Telnyx before, invites are capped at 10 open / 10 per hour,
sub-members cannot own connections or outbound profiles, and Telnyx itself recommends
sub-members just use the owner's API key — which would collapse the per-SDR isolation the FAQ
describes. The Managed Accounts route is the documented multi-tenant primitive, but it is
sales-gated to enterprise.

**NOT DOCUMENTED — whether Verified Numbers are scoped per Managed Account.** No page states
whether a number verified inside Managed Account A is visible to, or usable by, Managed
Account B or the manager account. The FAQ speaks only about organization owner vs sub-user.

**NOT DOCUMENTED — whether the same phone number can be verified concurrently on two
different Telnyx accounts / Managed Accounts.** This matters directly: an SDR who changes
employer, or a number reused across tenants, has undefined behaviour. Note the adjacent
documented rejection **D36 — "You are attempting to make an outbound call with a caller ID of
a number which belongs to another Telnyx user"**
(https://support.telnyx.com/en/articles/4409457-telnyx-sip-response-codes), which suggests
cross-account CLI collisions are actively policed for Telnyx-owned numbers, but the docs do
not say how this interacts with verified external numbers.

**NOT DOCUMENTED — how an API key maps to "sub-user" for verification purposes.** If Vocify
holds one org-owner API key and verifies every SDR's number through it, the FAQ implies all
those numbers become usable by all users — i.e. no per-tenant isolation. The docs neither
confirm nor deny this.

*To resolve:* ask Telnyx explicitly: (1) is a Verified Number scoped to a Managed Account?
(2) can the same E.164 be verified on two Managed Accounts at once? (3) if we verify all
tenants' numbers under one org-owner key, is there any mechanism at all to prevent tenant A
dialling with tenant B's verified CLI, or must that be enforced entirely in our application?

---

### Q5. Using the verified number as outbound CLI

**DOCUMENTED — Call Control / Voice API field.** `POST /v2/calls` takes `from`: "The `from`
number to be used as the caller id presented to the destination (`to` number). The number
should be in +E164 format." There is also `from_display_name` (SIP From Display Name, max
128 chars) and `privacy` (`id` | `none`). Source:
https://developers.telnyx.com/api-reference/call-commands/dial

**DOCUMENTED — SIP header priority (SIP Trunking).** Telnyx reads the caller ID from these
headers, highest priority first, and when more than one is present **only the highest is
used**:
1. `P-Preferred-Identity` (User part)
2. `P-Asserted-Identity` (User part)
3. `Remote-Party-Id` (User part)
4. `FROM` (User part)

The Verified Numbers article adds: "You need to make sure that you send the now verified
number in one of these headers and take into account the order priority." Sources:
https://support.telnyx.com/en/articles/6988813-verified-numbers,
https://support.telnyx.com/en/articles/3546251-caller-id-number-policy,
https://developers.telnyx.com/docs/voice/sip-trunking/configuration/caller-id-policy.md

**DOCUMENTED — connection-level override exists.** `ani_override` / `ani_override_type` on
credential/FQDN/IP connection outbound settings ("Caller ID Override" in the portal) sets a
number displayed on all outgoing calls from that connection; "Connections with Caller ID
Override enabled can send any format for outbound calls, **bypassing standard validation
rules**." Also `localization` (ISO 3166-1 alpha-2) governs which national dialling formats
are accepted; default `US`, and "If a Connection does not have a Localisation Country and the
number dialled appears to be invalid, Telnyx will attempt to validate the number using USA
as the Localisation Country." Sources:
https://developers.telnyx.com/docs/voice/sip-trunking/configuration/caller-id-policy.md,
https://support.telnyx.com/en/articles/3546251-caller-id-number-policy

**DOCUMENTED — behaviour with an UNVERIFIED non-Telnyx from-number: hard rejection, not
silent substitution.** "A call attempt using a non-Telnyx number that has not been verified
will be rejected with a **'403 Unverified Caller Origination Number D51'** SIP error." The SIP
code reference lists it as "**D51 - 403 Unverified origination number D51**". Sources:
https://support.telnyx.com/en/articles/6988813-verified-numbers,
https://support.telnyx.com/en/articles/4409457-telnyx-sip-response-codes
There is **no** documented silent-substitution behaviour anywhere.

**DOCUMENTED — the policy has been enforced since 15 Feb 2023.** "After February 15th, 2023,
Telnyx users will not be able to make calls from unverified numbers that have not been ported
to Telnyx." Source: https://support.telnyx.com/en/articles/6790265-verified-numbers-faq

**DOCUMENTED — other rejection codes that apply to an external-CLI model.**
- `403 D35` — Invalid Caller Origination Number (bad format; must be +E.164 in
  `FROM`/`PAID`/`RPID`).
- `403 D36` — CLI belongs to another Telnyx user.
- `403 D54` — "Outbound call rejection based on the originating caller ID number, which is
  currently restricted from originating outbound calls through Telnyx due to reputation
  concerns and risk validations. This restriction is based on multiple external reputation
  databases, which Telnyx uses to block spam traffic."
- `503` — international spoofing; documented fix "Use a valid origination number for the
  destination country".
- `403 D60` — "Can not make calls to non-verified numbers at this account level" (this one is
  about the **destination** number on low-tier accounts, not the CLI — do not confuse it
  with D51).
Sources: https://support.telnyx.com/en/articles/4409457-telnyx-sip-response-codes,
https://developers.telnyx.com/docs/voice/sip-trunking/configuration/caller-id-policy.md

**DOCUMENTED — verification does not exempt you from caller-ID policy.** "Please take note
once numbers are verified and you make outbound calls from them, our caller ID policy will
apply." Source: https://support.telnyx.com/en/articles/6988813-verified-numbers

**NOT DOCUMENTED — whether enabling Caller ID Override bypasses the D51 verification
requirement.** The override is documented as bypassing *format* validation only. Whether an
`ani_override` set to an unverified external number would still be D51-rejected is not
stated. This is a material gap: it is exactly the escape hatch a naive implementation would
reach for.

**NOT DOCUMENTED — interaction between a verified +34 CLI and the `503` "international
spoofing" rule.** The rule says outbound calls to international destinations with spoofed
caller IDs are rejected. A Spain-CLI-to-Spain-destination call is not cross-border at the
CLI/CLD level, and the documented remedy ("use a valid origination number for the destination
country") actually points *towards* a +34 CLI being correct. But no page states that
Verified-Number status is what makes a non-Telnyx +34 CLI count as "valid" rather than
"spoofed" on the route into Spain.

**NOT DOCUMENTED — whether Verified Numbers must also be permitted by the Outbound Voice
Profile, or whether STIR/SHAKEN attestation level differs for verified vs owned numbers.**
(Telnyx markets "A-level STIR/SHAKEN attestation" on https://telnyx.com/global-coverage, but
STIR/SHAKEN is a North American framework and is not relevant to Spanish termination; no page
ties attestation level to Verified Numbers.)

---

### Q6. Spain specifically

#### (a) Outbound calls to Spain

**DOCUMENTED — Spain is in coverage.** Spain (🇪🇸) appears in Telnyx's coverage listings, and
Telnyx claims 130+ countries of local calling, 230+ countries for international SIP trunking,
and carrier licenses in 30+ countries. Sources: https://telnyx.com/global-coverage,
https://telnyx.com/products/global-communications
**DOCUMENTED — destinations are gated by the Outbound Voice Profile.** "Telnyx supports 255
destinations across 10 regions. Enable destinations by region or individual country. Many
destinations require **Level 2 verification** before activation." `whitelisted_destinations`
takes alpha-2 country codes. Sources:
https://developers.telnyx.com/docs/voice/sip-trunking/configuration/outbound-voice-profiles,
https://telnyx.com/release-notes/new-special-destinations-available
**DOCUMENTED — Level 2 is required for international calling** ("Buy international numbers",
"Enable international calling and call forwarding" are listed as Level 2 capabilities).
Source: https://support.telnyx.com/en/articles/1130595-account-verification

**DOCUMENTED — and this is the single most operationally important Spain-adjacent clause
Telnyx publishes — the EEA PAI requirement:**
> "⚠️ Important - EEA Destinations: Calls terminating into the EEA internationally must
> include a valid P-Asserted-Identity (PAI) header containing a real, dialable CLI. This is
> used by downstream carriers for origination-based routing (OBR) billing. If the PAI header
> is: • Missing • Contains an anonymous value • Contains an invalid number … the call may be
> rejected or subject to surcharges from the terminating carrier which will be passed onto
> the customer. **Anonymous or invalid CLIs on these routes are not supported and can result
> in significant additional costs.**"

Source: https://support.telnyx.com/en/articles/3546251-caller-id-number-policy
Spain is in the EEA, so this clause governs Vocify's traffic directly.

#### (b) Using a Spanish CLI

**DOCUMENTED — CLI/CLD numbering-database validation is NANPA-only.** Telnyx's June 2022
enhanced validation checks CLI and CLD against *North American* national numbering databases,
and "CLI and CLD Validation will be applied to all outbound calls **between NANPA … numbers**",
with the applicable geographies explicitly enumerated (US and territories, Canada, Bermuda,
and Caribbean NANP members). It cannot be disabled. Separately: "CLI validation will be
applicable to all numbers used to perform outbound calls through the Telnyx network,
regardless of the number provider." Source:
https://support.telnyx.com/en/articles/6247033-cli-cld-validation-faq

**NOT DOCUMENTED — any Spain-specific CLI rule, validation, or allowed-range table on Telnyx.**
There is no equivalent of the NANPA database check documented for +34, and no Telnyx page
states which +34 ranges are acceptable as CLI.

**NOT DOCUMENTED — whether CLI is stripped, replaced, or mutated on Telnyx's routes into
Spain.** No Telnyx page addresses this. The only adjacent documented facts are the EEA PAI
clause above (which implies CLI is *carried* and is used for OBR billing) and the legacy
`D34 - 403 Source country is not from EEA` code, described as applying when "the customers
Outbound Voice Profile service plan is set to EEA but the caller ID in the SIP INVITE is not
from EEA", and explicitly flagged as "a legacy code [that] will generally not be seen anymore
as our service plans have since changed". Source:
https://support.telnyx.com/en/articles/4409457-telnyx-sip-response-codes

#### (c) Requirements to purchase a Spanish number (KYC)

**DOCUMENTED**, from https://support.telnyx.com/en/articles/1311073-spain-did-requirements
(article dated 26 May 2026):

*Local, Toll-Free and Shared-Cost numbers in Spain*
- Personal identity: name, last name, contact phone number, **local copy of ID or passport**,
  **Spanish National ID (DNI) or Foreigners' Identity Number (NIE)**.
- Business identity: name/last name of an authorised representative, contact phone number,
  company name, **local Company registration certificate**, **CIF (Certificado de
  Identificación Fiscal)**.
- Address: **address matching the DID area code** (street, building number, postal code,
  city, country) + **proof of address dated within 3 months**.
- "**End-users must be physically present in the country when purchasing numbers from that
  country.**"

*National numbers in Spain*
- Personal identity: name, last name, contact phone number, local passport or ID copy
  (**no DNI/NIE line item**).
- Business identity: authorised representative, contact phone, company name, local company
  registration certificate (**no CIF line item**).
- Address: **address in Spain** (not required to match an area code) + proof of address
  within 3 months; same physical-presence note.

*Cross-cutting*
- "**approximately 72 hours to validate the information and activate the number**".
- EU exception: "customers within the European Union may use a valid passport or national
  identity card from **any EU member state**, even if it differs from the EU country
  associated with the order; in these cases, the document will be treated as local." Telnyx
  reserves the right to request more documents or decline any.
- Available Spain local area codes listed by Telnyx: **910 Madrid, 930 Barcelona, 960
  Valencia, 979 Palencia, 945 Álava** (https://telnyx.com/phone-numbers/spain). Note these are
  91x/93x-family geographic ranges, i.e. the ranges TDF/149/2025 permits.
- Porting a Spanish number requires LOA, CIF/NIF, latest invoice, authorised person's
  passport/ID, number type (Analog Geographic / PBX Geographic / Intelligent Network), proof
  of address. Source: https://support.telnyx.com/en/articles/3267595-spain-number-porting

#### (d) Orden TDF/149/2025

**DOCUMENTED — yes, Telnyx does address it, but only on a marketing page, not in developer
docs or the support centre.** From https://telnyx.com/phone-numbers/spain, under "Local Spain
regulations", verbatim:
> "**Since June 2025, the use of mobile numbering ranges (numbers beginning with 6 or 7) for
> unsolicited commercial calls is prohibited** under Order TDF/149/2025, with only toll-free
> 800/900 numbers permitted for outbound marketing; businesses must consult the Lista Robinson
> before sending personalized advertising, as outlined by Bird & Bird."

Also documented on the same page:
- "**LSSI Article 21 requires express consent for commercial communications** with a narrow
  soft opt-in exception for existing customers; the Lista Robinson is managed by Adigital…
  as a free opt-out registry".
- "**Violations carry fines of up to EUR 600,000** for very serious offences… EUR 30,001–150,000
  for serious offences, and up to EUR 30,000 for minor infractions; **sending more than three
  commercial communications to one recipient within a year constitutes a serious offence**."

**This is the decisive finding for the product design.** Telnyx's own published position is
that Spanish **mobile** numbering (6xx/7xx) may **not** be used for unsolicited commercial
calls. Vocify's model — SDRs presenting their **own personal mobile** — is precisely the
pattern Telnyx names as prohibited, if the calls are unsolicited commercial calls. An SDR's
**office landline (91x/93x geographic)** is not caught by the mobile prohibition.

**NOT DOCUMENTED — how Telnyx enforces this.** There is no documented network-level block,
no documented rejection code for a +34 mobile CLI on a call to Spain, and no documented
screening at verification time. The statement is advisory ("businesses must comply"), placed
on a number-purchasing page.

**NOT DOCUMENTED — whether Telnyx's Verified Numbers flow refuses to verify, or refuses to
present, a +34 6xx/7xx number given this rule.** The two facts sit on different pages with no
cross-reference.

**NOT DOCUMENTED — Telnyx's reading of Article 4 (operators must block empty or unassigned
CLI) or Article 9 (mobile-numbering prohibition) as obligations on Telnyx itself as a
licensed operator.** Telnyx says it holds carrier licences in 30+ countries
(https://telnyx.com/global-coverage) but does not publish a TDF/149/2025 compliance statement.

#### Note on non-Telnyx sources for TDF/149/2025

Third-party legal/industry summaries I read (Bird & Bird via Telnyx's own citation, plus
https://talk-q.com/outbound-call-regulations-in-spain, https://glofera.com/en/order-tdf-149-2025-make-calls-and-send-sms-from-your-company/,
https://www.telemediamagazine.com/spain-unveils-tough-new-crackdown-on-outbound-calls-and-caller-id-transparency/)
describe the Order as: published in the BOE 15 Feb 2025, effective 7 Jun 2025; Article 4
requiring operators to block calls with empty CLI or CLI not assigned in the National
Numbering Plan; Article 9 prohibiting mobile ranges for unsolicited commercial calls and
customer-service calls; operators required to block calls using Spanish ranges that originate
abroad or present spoofed Spanish CLI; and permitted alternatives described as **geographic
(91x, 93x…) or 800/900**. These are **not Telnyx sources** and are flagged as such; they are
included only because they conflict with Telnyx's narrower wording (see Contradictions).

---

### Q7. Anti-spoofing / policy risk

**DOCUMENTED — the AUP's CLI clause.** Prohibited: "using **Telnyx numbering resources**
(numbers in Customer's Mission Control portal account or provided by Telnyx to Customer) as
the Calling Line Identification (CLI) in any manner which Telnyx, **in its sole discretion**,
constitutes as fraud, deceptive or spam and regardless of whether such usage take place on
Telnyx's network or other networks (e.g., spoofing a Telnyx CLI)". Source:
https://telnyx.com/acceptable-use-policy

**DOCUMENTED — the AUP's illegality hook.** Services may not be used "in connection with the
violation of or to violate any Laws", where "Laws" expressly includes "applicable
international, federal, state, or local law… as pertaining to… **telemarketing or other
inappropriate selling**, data privacy (including… the General Data Protection Regulation…)"
and "anti-spam and other laws and regulations regarding unsolicited advertising, marketing or
other similar activities". Source: https://telnyx.com/acceptable-use-policy
**Consequence:** a breach of Orden TDF/149/2025 or LSSI Art. 21 is therefore also an AUP
breach, independent of anything Telnyx says about CLI.

**DOCUMENTED — other AUP clauses that bear on an outbound SDR dialer.** Prohibited:
- "**auto-dialing or predictive-dialing** (sometimes referred to as 'robo-dialing')";
- "sending **unsolicited calls**… if such unsolicited activities could reasonably be expected
  to or do in fact provoke complaints";
- "**low answer seizure rate (ASR)** as determined by Telnyx";
- "**Abandoned Call**[s]" (calls that do not result in a completed connection or are
  terminated before being answered) "in excess of thresholds set forth by Telnyx in its sole
  discretion";
- "use of call Services in a manner which **does not consist of uninterrupted live human voice
  dialog by and between natural human beings**";
- "**falsifying User or other identifying information** provided to Telnyx or to other Users
  of the Services";
- "impersonate or misrepresent any person or entity";
- "use of call Services in excess of certain **call per second (CPS)** thresholds".
Source: https://telnyx.com/acceptable-use-policy
Telnyx "reserves the right to enforce, waive, or remedy any violation… in its sole
discretion" and may "assess additional charges or surcharges".

Human-initiated click-to-call with a live SDR appears to satisfy the "uninterrupted live human
voice dialog" clause and to sit outside the auto/predictive-dialing prohibition, but the
unsolicited-calls, ASR, and abandoned-call clauses are all discretionary and would apply to
cold-calling volume.

**DOCUMENTED — country-specific contractual term.** "Fraud Prevention: Customer shall not
use, or permit the use of, the Services for any unlawful, fraudulent, misleading, or abusive
purposes, including spam, **spoofing**, or harassment. Customer shall implement reasonable
technical and operational measures to prevent such misuse…" Source:
https://telnyx.com/country-specific-requirements-terms-and-conditions-of-service

**DOCUMENTED — reputation-based CLI blocking is real and automated.** `403 D54` blocks
outbound calls based on the originating caller ID's standing in "multiple external reputation
databases". Source: https://support.telnyx.com/en/articles/4409457-telnyx-sip-response-codes
An SDR's personal mobile that accumulates spam reports could be blocked at Telnyx without any
account-level action.

**DOCUMENTED — the stated purpose of Verified Numbers, which creates a semantic gap.**
"Ensuring that our customers are **using numbers they own** for outbound calling, reduces the
risk of malicious use cases on the Telnyx network." Source:
https://support.telnyx.com/en/articles/6790265-verified-numbers-faq
In Vocify's model, the number is owned by the SDR (an end user of a tenant), not by the Telnyx
customer. The FAQ does not address whether "customer" extends transitively to end users. The
AUP's definition of "Users" is broad — "customer (including Customer) of Telnyx **and its
customers and/or end users**" — which arguably covers the SDR, but nothing states that
end-user ownership satisfies the Verified Numbers ownership requirement.

**NOT DOCUMENTED — whether "each end-user verifies their own personal mobile and we present
it" is a policy violation.** No Telnyx page prohibits, permits, or describes this pattern.
The nearest documented signals are: (i) the >200-number bulk path is described as a
"**reinforced KYC process**" run with an account manager, implying Telnyx scrutinises exactly
this kind of many-external-numbers profile; (ii) the sole-discretion CLI clause; (iii) the
ownership framing above. None is dispositive.

**NOT DOCUMENTED — any suspension trigger, warning threshold, or appeals path specific to
Verified Numbers.**

---

## Open questions requiring a Telnyx sales/support answer

1. **[Blocking] Verified Numbers country coverage.** Provide the supported-country matrix.
   Specifically: can a **+34 mobile (6xx/7xx)** be verified via `sms`? Can a **+34 geographic
   landline (91x/93x)** be verified via `call` and via `dtmf`? Is there any country the
   feature does not work in?
2. **[Blocking] Spain + mobile CLI under TDF/149/2025.** Telnyx's own Spain page says mobile
   ranges are prohibited for unsolicited commercial calls. Will Telnyx (a) verify a +34 mobile
   at all, (b) carry a call into Spain presenting a +34 mobile CLI, and (c) does Telnyx treat
   this as an AUP breach on the customer's side? Get this in writing.
3. **[Blocking] Multi-tenant scoping.** Are Verified Numbers scoped per Managed Account? Can
   the same E.164 be verified concurrently on two Managed Accounts? If we verify all tenants'
   numbers under a single org-owner API key, is there **any** platform-side mechanism
   preventing tenant A from dialling with tenant B's verified CLI, or is that entirely our
   responsibility?
4. **Managed Accounts access.** We would need Managed Accounts (enterprise, sales-created,
   limited release) for real tenant isolation. What is the qualification bar, lead time, and
   is there a per-Managed-Account minimum spend?
5. **Verified Numbers caps and lifetime.** Maximum verified numbers per account and per
   Managed Account? Do verifications ever expire or require re-verification? What are the
   actual rate limits on `POST /v2/verified_numbers` (values, window, scope)?
6. **Caller ID Override vs D51.** Does setting `ani_override` on a connection bypass the
   Verified Numbers requirement, or is D51 still returned? (We need this answered explicitly
   so we do not accidentally build on an unsupported bypass.)
7. **Spain route CLI integrity.** On Telnyx's route(s) into Spain, is the CLI passed
   transparently in PAI end-to-end? Is it ever rewritten, truncated, or replaced? Any known
   Spanish-carrier blocking of foreign-originated traffic presenting +34 CLI (the Article 4 /
   foreign-origin-with-Spanish-CLI blocking that third-party analyses describe)?
8. **`dtmf` verification method status.** It is documented in the support centre but is not in
   the published OpenAPI enum, and is labelled BETA. Is it GA? Is it contract-stable? Is it
   available in Spain?
9. **Bulk / reinforced KYC.** For a SaaS onboarding hundreds of SDR-owned numbers, what
   evidence does the reinforced KYC process require, and can it be satisfied per-tenant rather
   than per-number?
10. **Account level for pilot.** Confirm we will be Level 2 (international calling + Spain
    destination in the Outbound Voice Profile) before testing, so results are not confounded
    by trial/L1 caps (1 verified number, 100 calls/day, 10 calls/hour, forced TTS disclaimer).

---

## Contradictions or ambiguities found

1. **`verification_method` enum omits `dtmf`.** The published OpenAPI — both the API-reference
   page and the consolidated `spec3.json` — restricts `verification_method` to
   `enum: [sms, call]`. Two support articles document `"verification_method": "dtmf"` with
   working cURL. The support centre is ahead of the spec (and the DTMF article is labelled
   BETA). Treat `dtmf` as undocumented-in-contract.
   (https://developers.telnyx.com/api-reference/verified-numbers/request-phone-number-verification
   vs https://support.telnyx.com/en/articles/13854980-beta-how-to-verify-phone-numbers-using-dtmf-press-1-to-verify)

2. **`verification_webhook_url` is documented in support articles but absent from the OpenAPI
   request schema.** The spec lists only `phone_number`, `verification_method`, `extension`.
   Same divergence as above.

3. **Flash call pricing exists for a method that is not documented as available.** The Verified
   Numbers pricing table includes a "Use Verified Number via Flash call" line
   ($0.03 + Flash pricing), but Flash call is not a `verification_method` for Verified Numbers
   anywhere — `flashcall` is documented as a channel of the separate **Verify 2FA** product.
   (https://support.telnyx.com/en/articles/6988813-verified-numbers vs
   https://developers.telnyx.com/docs/identity/verify/quickstart/index)

4. **"Mission Control Portal only" vs "REST API".** The FAQ says "Numbers can be verified
   through the Mission Control Portal" and defines a Verified Number as one verified "in the
   Mission Control Portal", with no mention of the API. The main article, the DTMF article and
   the 2023 release note all document the REST API. The FAQ appears stale.
   (https://support.telnyx.com/en/articles/6790265-verified-numbers-faq vs
   https://telnyx.com/release-notes/telnyx-verified-numbers)

5. **Sub-user exclusivity is hedged and conflicts with the Organizations documentation.** The
   FAQ: a sub-user-added verified number "**should be** available exclusively for that
   particular user only". The Organizations page: sub-accounts "**cannot 'own' most things in
   the system**", "not all our new V2 services are exposed to the organizations
   functionality", and "we **strongly recommend that sub members leverage the API key of their
   organization owners account**". If sub-members are using the owner's API key, per-sub-user
   verified-number exclusivity cannot hold. These two pages cannot both be operationally true.

6. **Telnyx's TDF/149/2025 summary is narrower than the third-party sources it cites.** Telnyx
   writes "with **only toll-free 800/900 numbers permitted for outbound marketing**". The
   third-party analyses (including the Bird & Bird piece Telnyx links to, as relayed by
   Telemedia and Glofera) describe permitted numbering as **geographic landline ranges (91x,
   93x…) OR 800/900**. If Telnyx's stricter reading is correct, even an SDR's office landline
   would be non-compliant for outbound marketing — which would eliminate the landline
   fallback too. **This needs a legal answer, not a docs answer.**

7. **"Spoofing" is defined inconsistently across Telnyx pages.** The AUP's CLI clause is scoped
   to "**Telnyx numbering resources** (numbers in Customer's Mission Control portal account or
   provided by Telnyx to Customer)". A verified external number is arguably "a number in
   Customer's Mission Control portal account" (it appears in the Verified Numbers section) but
   is certainly not "provided by Telnyx". Meanwhile the caller ID policy flatly says
   international spoofing is rejected with `503`, and the developer-docs version says the fix
   is to "use a valid origination number for the destination country" — which implies a
   verified in-country CLI is the *correct* answer rather than spoofing. No page reconciles
   these.

8. **Level-2 "full access" vs undocumented Verified Numbers caps.** The Verified page says
   "Full access except otherwise specified below" and does not mention Verified Numbers,
   which reads as "no cap" — but it also reserves the right to "modify limitations without
   notification". Absence of a documented cap is not a guarantee of no cap.

9. **A search-engine synthesis asserted that Spanish +34 numbers can be used as verified
   caller ID.** No fetched Telnyx page supports that claim. It is recorded here as an
   inference by a search tool, **not** as a Telnyx statement, and should not be relied on.

10. **`D34 - 403 Source country is not from EEA`** is documented but simultaneously described
    as "a legacy code [that] will generally not be seen anymore as our service plans have
    since changed on our outbound voice profile offering". Whether any EEA-service-plan
    CLI-origin check still exists is therefore unclear.
