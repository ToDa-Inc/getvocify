# HubSpot Native Calling — Caller ID Model (research findings)

Research date: 2026-08-27. All claims below are marked DOCUMENTED (with the URL actually fetched) or NOT DOCUMENTED.
Every quotation is verbatim from the fetched HubSpot page.

---

## HEADLINE

1. **Yes — HubSpot ships a production feature that presents the user's OWN existing number as caller ID.** It is called
   **"Register an outbound phone number"** (a.k.a. "Outbound phone numbers (personal/office lines)"). Verification is by
   **SMS code OR voice-call code, user's choice**. DOCUMENTED.

2. **But for Spain specifically, HubSpot documents that this does not work — the call fails.** HubSpot names
   Order TDF/149/2025 and states that calls presenting a Spanish caller ID from *any HubSpot registered number* "may
   receive an error message, and the call will not be completed." DOCUMENTED.

So the user's report ("connected outbound calling in HubSpot, Twilio-backed, it WORKED including caller ID") is **not
evidence that presenting your own Spanish mobile CLI is enforceable-in-practice**. HubSpot's own docs say the opposite
for Spain. See "Reconciling the user's report" at the bottom.

---

## Q1 — Does HubSpot let a user place outbound calls displaying the user's OWN existing phone number as caller ID?

**DOCUMENTED — YES.**

Exact feature name: **"Register an outbound phone number."** In the UI the control is Settings → General → Calling tab →
**Add phone number**. In HubSpot's conceptual doc the category is called **"Outbound phone numbers (personal/office
lines)."**

Source: https://knowledge.hubspot.com/calling/register-an-outbound-phone-number (last updated May 14, 2026)

> "Registering an outbound phone number allows you to make calls from the HubSpot CRM while displaying your existing
> mobile or office number as the Caller ID. This ensures that when you call a prospect or customer, they see a familiar
> or local number, increasing the likelihood of a successful connection."

> "Unlike HubSpot-provided numbers, HubSpot does not own these numbers. They are used for outbound identification
> purposes only. Inbound calls to these numbers will continue to ring on your personal device or landline as they
> normally do, rather than ringing within the HubSpot browser."

### Verification flow (DOCUMENTED — both SMS and voice offered, user chooses)

Verbatim steps from the same page:

> 4. To register you phone number, click **Add phone number**.
> 5. In the dialog box, enter your **phone number**, and an **extension**, if applicable.
> 6. You will be prompted to verify your phone number. You can choose how the verification code is delivered to you by
>    clicking **SMS message** or **Phone call**.
> 7. Click **Text me** or **Call me**.
> 8. When prompted, enter the **verification code** from your text or call.
> 9. Click **Save**.

Corroborated at https://knowledge.hubspot.com/calling/manage-phone-numbers-registered-for-calling:

> "Individual setup: unlike HubSpot-provided phone numbers, these cannot be assigned by an admin. Every sales rep must
> manually verify their own number via an SMS code or a phone call code."

Mechanism named: this is Twilio's **verified caller ID** primitive (HubSpot uses that exact term — see Q4).

### Constraints on registration (DOCUMENTED)
- Per-user, not per-org: "even if a number is shared across an office, each individual HubSpot user must register the
  number separately in their own account to use it as their personal Caller ID."
- "You cannot register a toll-free number to use as an outbound phone number."
- Requires an assigned paid *Sales Hub* or *Service Hub* seat (Starter/Professional/Enterprise).
- Country must be on the supported list.

---

## Q2 — "HubSpot-provided phone number" vs "Outbound phone number" — the precise distinction

**DOCUMENTED.** These are two genuinely different products and HubSpot has a dedicated comparison page.

Source: https://knowledge.hubspot.com/calling/manage-phone-numbers-registered-for-calling ("Set up calling", last updated
April 14, 2026)
Source: https://knowledge.hubspot.com/calling/acquire-and-validate-hubspot-provided-phone-numbers (last updated Aug 5, 2026)

### A. HubSpot-provided phone number

> "HubSpot-provided phone numbers are generated directly within your HubSpot account and are powered by Twilio. Because
> these numbers are created and managed within HubSpot, you gain full control over the entire lifecycle of a phone call."

- **Ownership:** a NEW line, provisioned by/owned by Twilio on HubSpot's behalf. Not a number you previously had.
- **Caller ID presented to callee:** the HubSpot-provided (Twilio-owned) number itself.
- **Inbound:** yes — rings in HubSpot browser/mobile app; supports Help Desk / Conversations Inbox shared lines, IVR
  routing, voicemail integrated with CRM, recording-consent messages.
- **Admin-controlled:** "Super Admins acquire and assign these numbers to specific users or teams."
- **Regulatory review:** REQUIRED. "because these are new lines, they require a one-time regulatory review (through
  Twilio) to verify your business identity before they can be activated." Acquisition flow: "Based on the country you
  selected, you may need to submit your business information to Twilio for a one-time, country specific regulatory
  review and local telecom confirmation." 3–4 business days for approval; "Certain countries and number types can take
  between 1-6 weeks to provision."
- Pooled per-subscription limit; extra numbers are a paid add-on.
- "HubSpot-provided phone numbers do not support incoming calls from private or anonymous numbers."

### B. Outbound phone number (registered / personal / office line)

> "Outbound phone numbers are existing lines you already use, such as a personal mobile phone or an office desk phone.
> When you register one of these numbers in your HubSpot account, you are not transferring ownership or moving the number
> into HubSpot. Instead, you are verifying that the number belongs to you so HubSpot can display it as your Caller ID
> when you place outbound calls from the CRM."

- **Ownership:** you keep it with your existing carrier. HubSpot/Twilio do NOT own it.
- **Caller ID presented to callee:** your own existing number. "when you call a prospect from the CRM, their phone will
  show your actual office or mobile number. If they call you back, the call goes directly to your physical device,
  bypassing HubSpot."
- **Outbound only:** "since HubSpot doesn't own the infrastructure for these lines, you cannot receive inbound calls in
  the browser, and you cannot use HubSpot to record or transcribe any return calls you receive on these lines."
- **Regulatory review:** NONE. "there is no regulatory review process. You can verify a number and start calling with
  your personal Caller ID more quickly."

### Feature matrix (verbatim from HubSpot's table)

| Capability | HubSpot provided phone number | Outbound phone number |
| --- | --- | --- |
| Call from CRM | Yes | Yes |
| Call from Conversations Inbox or Help Desk | Yes | Yes |
| Route to forwarding number, voicemail, etc. | Yes | No |
| Log outbound calls to CRM | Yes | Yes |
| Log inbound calls, missed calls, and voicemails to CRM | Yes | No |

### C. A third, separate thing — do not conflate: "Twilio Connect"

Bring-your-own-Twilio-account. Requires Sales/Service Hub **Professional or Enterprise** seat. Used to call countries not
on HubSpot's supported list and to buy minutes directly from Twilio. Here the carrier relationship is *yours*, directly
with Twilio, and the CLI is whatever you have verified/own in your own Twilio account.
Source: https://knowledge.hubspot.com/calling/hubspot-calling-minutes (title: "Set up a Twilio Connect account in HubSpot")

> "If you have an assigned Sales Hub or Service Hub Professional or Enterprise seat, you can set up an account with the
> third-party calling provider Twilio Connect to make calls in HubSpot and make calls to countries that are not included
> on the supported country list."

Note: the Twilio Connect flow uses Twilio's own **"Verified Caller IDs"** section, i.e. the same verified-CLI primitive.
(That detail appears in a HubSpot Community troubleshooting thread, not in the KB:
https://community.hubspot.com/t/troubleshooting-error-adding-your-phone-number-to-twillio-connect/20277 — community post,
treat as lower authority than KB.)

### C2. A fourth path, and the one that actually resolves Spain: PORTING

Source: https://knowledge.hubspot.com/calling/port-out-a-hubspot-phone-number ("Port a number to HubSpot", upd. Jul 30, 2026)

This is the middle path between "my own number" and "a brand new number", and it is the remedy HubSpot recommends in
every blocked-CLI country note. It converts your existing number into a HubSpot-provided-class number:

> "Number porting is the process of moving a telephone number from one calling carrier to another. **Porting your existing
> phone number to HubSpot makes HubSpot the owner of that phone number.** Upon completion of the port, that number will be
> considered a 'HubSpot Number' which enables those numbers for inbound and outbound calling in HubSpot, IVR, team
> calling in Help Desk and Inbox, and more."

**Spain IS portable — but "Spain(local)" only.** Verbatim from the "Available countries for porting" list: Australia(local),
Austria(local), Brazil(local), Canada(local), Denmark(local), Finland(local and mobile), France(local), Germany(local),
Ireland(local), Italy(local), Mexico(local), Netherlands(local), New Zealand(local), Norway(local), **Spain(local)**,
Sweden(local), Switzerland(local), United States(local, mobile, and toll-free), United Kingdom(local and mobile).

So across all three Spain-relevant lists — provided numbers, porting, and compliant numbering — HubSpot is
**local/geographic-only for Spain, never mobile.** That triple consistency is itself strong evidence that Spanish mobile
CLI for commercial outbound is genuinely dead, not just discouraged.

Other documented details:
- "Porting can take 2 to 4 weeks to complete for U.S. numbers, and 4 to 6 weeks for other countries."
- "Non-US countries will be taken to a regulatory flow where they must submit business information for approval. This
  ensures your business complies with using phone numbers for that country."
- Confirms the carrier again: "The new calling provider should submit a port out request to **HubSpot's call carrier,
  Twilio**."
- Twilio-to-Twilio ports are cheaper/faster: "Porting numbers from platforms that also use Twilio as the calling provider
  do not require an LOA or additional documentation."

**Key implication:** porting is *not* "keep your own number and spoof it." Ownership genuinely transfers to
HubSpot/Twilio, which is precisely why it satisfies the Spanish rule — the CLI is then legitimately allocated to the
originating carrier. You lose the number from your own PBX/handset in the process.

### D. Fifth thing, also distinct: "Number verification" / business profile / CNAM

Source: https://knowledge.hubspot.com/calling/set-up-number-verification-to-improve-call-trust-and-deliverability
(last updated June 22, 2026)

This is about **caller NAME (CNAM) and trust products**, not about which *number* is displayed. Critical scope limits:

> "Caller ID is displayed only if the recipient has turned on the CNAM feature on their phone through their carrier."
> "CNAM currently only works on US phone numbers."
> "Solutions like STIR/SHAKEN and voice integrity are unlocked in your approved business profile. These solutions
> currently only apply to US-based, HubSpot-provided phone numbers."

So: STIR/SHAKEN attestation and CNAM in HubSpot are **US-only and HubSpot-provided-only**. There is no documented
equivalent attestation path for a registered Spanish number. Business profile approval takes 7–10 business days; asks for
an **EIN** (US employer identification number), which itself signals US-centric design.

---

## Q3 — Supported countries, and Spain specifically

**DOCUMENTED. There is an authoritative country list page.**

Source: https://knowledge.hubspot.com/calling/what-countries-are-supported-by-calling
("Supported countries for HubSpot calling", last updated **June 23, 2026**)

The page contains **two different lists** that must not be conflated:

### List 1 — Supported countries for calling (applies to BOTH number types)

> "When making calls from HubSpot using either a registered outbound phone number or a HubSpot-provided phone number, the
> countries listed in the table below are supported. Any overseas territories that use the same international country
> code as the countries in this list are supported as well."

**Spain IS in this table** — with a large restriction note (full text in Q4).

Countries in the table (with a "Restrictions" column per row) include: Argentina, Australia/Cocos/Christmas Island,
Austria, Belgium, … Finland/Åland Islands, France, … Japan, … Norway, … Slovenia, South Africa, South Korea, **Spain**,
Sweden, Switzerland, Taiwan, Thailand, United Kingdom, United States/Puerto Rico. (Table is ~60 rows; I read the rows
relevant to CLI enforcement.)

Also on that page:
> "HubSpot also limits calls made to special service numbers and numbers with a high risk of fraud."
> "you must have an assigned Sales Hub or Service Hub paid seat to register your phone number with one of the countries
> listed below."

### List 2 — Countries where HubSpot-PROVIDED numbers are available

> "Currently, HubSpot only offers HubSpot-provided phone numbers from the countries listed below. You do not have to be
> located in one of those countries to use a HubSpot-provided phone number; however, some country regulations vary on
> whether or not they require a local address."

**Spain appears as: "Spain (local)"** — i.e. **geographic/fixed only. NOT mobile.**

This is meaningful: other countries in the same list are marked "(mobile and local)" (e.g. Germany, Netherlands, Poland,
Israel, Mexico, Denmark, Finland, Austria, Belgium, UK, US) or "(mobile)" (Portugal, Estonia, Nigeria, Hong Kong). Spain
is local-only. That is consistent with Order TDF/149/2025 banning mobile numbering for B2C commercial calling.

### Direct answers
- (a) **Spain supported for HubSpot-provided numbers → YES, but local/geographic (+34 9x) only.** DOCUMENTED.
- (b) **Spain supported for using your OWN registered number as caller ID → listed as supported, but HubSpot
  simultaneously documents that such calls fail.** DOCUMENTED. See Q4. In practice this is a "no."

---

## Q4 — THE CRUX: does HubSpot document that the registered number may NOT display / may be replaced or suppressed?

**DOCUMENTED — YES, extensively, and for Spain it is stronger than "may not display": the call does not complete.**

### 4a. Spain row, verbatim and complete (source: supported-countries page)

> "As of June 2025, The Ministry for Digital Transformation (Spain's regulatory authority for electronic communications)
> ([Order TDF/149/2025](https://www.boe.es/buscar/act.php?id=BOE-A-2025-2870)) prohibits the use of mobile phone numbers
> starting with the prefixes 346 and 347 for business-to-consumer (B2C) telemarketing or customer service calls. The
> order mandates the blocking of calls that falsely present a Spanish Caller ID but originate from international sources
> to combat spoofing practices. These measures aim to combat scam calls and enhance consumer protection by ensuring
> better identification of numbers used for commercial purposes. When you register a Spanish mobile number, this number
> is not owned by HubSpot's calling provider Twilio and utilizes verified Caller ID. As a result, if you are placing
> outbound B2C calls from registered Spanish mobile numbers starting with 346 or 347, **or placing calls that present a
> Spanish Caller ID (all HubSpot registered numbers), you may receive an error message, and the call will not be
> completed.**"

Read the parenthetical carefully. Two failure conditions are given:
1. registered Spanish **mobile** numbers with prefix 346/347 (i.e. +34 6…, +34 7…) doing B2C, and
2. **any** call "that present[ing] a Spanish Caller ID" — and the parenthetical "(all HubSpot registered numbers)" scopes
   this to the *registered* number category. HubSpot-provided numbers are excluded by contrast — they *are* owned by
   Twilio and are legitimately originated, which is exactly the distinction the sentence draws ("this number is not owned
   by HubSpot's calling provider Twilio and utilizes verified Caller ID").

Hedge to be honest about: HubSpot writes "**may** receive an error message," not "will always." NOT DOCUMENTED: any
per-carrier breakdown, rollout date of HubSpot's own enforcement, or whether HubSpot pre-blocks client-side vs. relaying a
carrier rejection.

### 4b. Generic caveat on the registration page itself

Source: https://knowledge.hubspot.com/calling/register-an-outbound-phone-number

> "Since outbound phone numbers are not owned by Twilio, and utilize verified caller ID, calls are more likely to be
> marked as spam and blocked by call carriers."

> "Calls to Singapore, Norway, and Australia using non-Twilio phone numbers may face connection issues due to regulatory
> measures."

This is HubSpot explicitly stating the structural weakness of the own-number model: not carrier-owned ⇒ spam-flagged and
blocked.

### 4c. Dedicated FAQ entry: caller ID replaced with "Unknown" / "No Caller ID"

Source: https://knowledge.hubspot.com/calling/calling-frequently-asked-questions (last updated Aug 14, 2026)

Section heading verbatim: **"Why are recipients seeing my caller ID displayed as 'Unknown' or 'No Caller ID'?"**

> "Telecom providers use a wide range of tools to identify suspicious callers and protect their users. Unfortunately, it's
> possible for legitimate businesses to be impacted by these tools; you can't fully control how calls are labeled since
> spam/scam decisions are made by telecom providers and call recipients. Approaches vary by provider and frequently
> change."

> "**HubSpot's calling allows you to use your own number for calling while still retaining it for personal use. This can
> occasionally contribute to caller ID issues.** If following best practices has not resolved caller ID issues, it is
> recommended to use one of HubSpot's calling partner integrations. This will involve acquiring a new number to place
> calls but should resolve any remaining caller ID issues."

> "If your usual outbound number is consistently blocked or labeled as spam, keep a HubSpot-provided number available as a
> fallback option for placing calls."

Also, on "Call Failed": > "If these solutions don't work, the carrier may have blocked the call due to the calling number
(caller ID)."

### 4d. The same pattern documented across many EU countries — this is the important structural evidence

All verbatim from the supported-countries page. Note every single one ends with HubSpot telling you to port or buy a
HubSpot-provided number:

- **Austria:** "Austrian operators are now required to **suppress or block** incoming international voice calls that use
  an Austrian national number as the CLI, across all Austrian number types (fixed and mobile), except for verified mobile
  roaming scenarios. If you are not located in Austria and are using a registered Austria number for outbound calling in
  this region, seek alternatives like porting or acquiring a HubSpot number."
- **Belgium:** "Under the Belgian Royal Decree on spoofing, Belgian operators are now required to **block** incoming
  international calls that present a Belgian E.164 number as the Caller ID. This applies to all Belgian number types,
  including geographic, non-geographic (070, 078, 0800, and 090x), mobile, and short numbers."
- **Finland / Åland Islands:** "Calls will be **blocked** if the Caller ID is a Finnish number but the call originates
  internationally (unless it's a verified mobile roaming scenario). Operators will also **suppress the CLI, resulting in
  an 'Anonymous' or 'Private' call**, if the number format is incorrect or uses specific prefixes like 0435."
- **Norway:** "the Norwegian Communications Authority (Nkom) requires Norwegian operators to **block** incoming
  international calls that present a Norwegian number as the Caller ID, with limited exceptions for verified roaming …
  if you call a Norwegian number, you must be in Norway. If you're outside of the country (or use a VPN that alters your
  location) and call a Norwegian number, your call may be blocked and the call may fail."
- **Switzerland:** "calls made to Switzerland using fixed or geographic numbers (like +41 2x…, +41 4x…) as a CLI are now
  likely to be **blocked or anonymized** by local carriers. Starting **July 1, 2026**, this enforcement will expand to
  mobile numbers (like +41 7x…)."
- **Japan:** "You can still make calls to Japan from a Japanese number registered in HubSpot, or any number registered in
  HubSpot, but **the Caller ID will be blocked on the outgoing call.**"
- **South Africa:** "Calls that present a South African mobile caller line identification (CLI) are not permitted. As a
  result, outbound calls placed from South African mobile numbers registered in HubSpot are unlikely to connect
  successfully."
- **Colombia:** "outbound calls placed from +57 lines to +57 lines are not supported … it's recommended you set up a
  HubSpot-provided Colombian number."
- **Taiwan:** "local outbound calls from registered +886 phone numbers are no longer supported in HubSpot."
- **Australia:** "calls from a registered outbound number to Telstra carrier numbers may fail due to Telstra's spam
  prevention settings. To avoid this issue, it's recommend you set up a HubSpot-provided Australian number."
- **France:** partial text captured — a change "from Arcep" under which "outbound calls from +336 and +337 numbers will no
  longer be supported. Starting June 1, 2025, …" (I did not capture the full France row verbatim; treat as partial.)

**Structural conclusion (my synthesis, not a HubSpot quote):** HubSpot at scale has *not* found a way to make
own-number/verified-CLI outbound work in jurisdictions that have implemented CLI-spoofing blocking. Its documented answer
in every such jurisdiction is to abandon verified-CLI and instead use a carrier-owned number (HubSpot-provided/Twilio),
port the number in, or hand off to a third-party provider with its own carrier relationship. Spain is squarely in that
group.

---

## Q5 — Who is the underlying carrier?

**DOCUMENTED — Twilio, stated publicly and repeatedly by name.**

- https://knowledge.hubspot.com/calling/calling-frequently-asked-questions —
  > "HubSpot calling is powered by Twilio, a Voice Over IP (VOIP) service that connects the call between you and the
  > number you're calling."
- https://knowledge.hubspot.com/calling/manage-phone-numbers-registered-for-calling —
  > "HubSpot-provided phone numbers are generated directly within your HubSpot account and are **powered by Twilio**."
- https://knowledge.hubspot.com/calling/acquire-and-validate-hubspot-provided-phone-numbers —
  > "Acquire a HubSpot-provided phone number (**powered by Twilio**)."
- https://knowledge.hubspot.com/calling/set-up-number-verification-to-improve-call-trust-and-deliverability —
  > "verifying this identity and your use cases through **our calling provider, Twilio**"
- https://knowledge.hubspot.com/calling/what-countries-are-supported-by-calling (Spain row) —
  > "this number is not owned by **HubSpot's calling provider Twilio**"
- https://knowledge.hubspot.com/calling/what-are-the-technical-requirements-to-use-the-calling-tool —
  > "HubSpot works with a third-party service, **Twilio**, for calling services."
  (also references a Twilio IP migration and Twilio network/port requirements)
- https://knowledge.hubspot.com/calling/hubspot-calling-minutes — Twilio Connect BYO-account path.

So the user's belief that it was Twilio-backed is correct and confirmed by HubSpot's own docs.

NOT DOCUMENTED: the downstream Spanish interconnect/wholesale carrier(s) Twilio uses for +34, and whether Twilio's
Spanish numbers are CNMC-registered in HubSpot's name or Twilio's.

---

## Q6 — Third-party calling providers (Aircall, Ringover, Kixie, etc.)

**Partly DOCUMENTED.**

DOCUMENTED — the integration model and that HubSpot's telephony is bypassed entirely:
Source: https://knowledge.hubspot.com/calling/integrate-a-third-party-calling-provider-with-hubspot (last updated Jan 30, 2026)

> "If you're already using a calling app, or if you need to call countries that aren't listed on HubSpot's supported
> countries list, you can integrate a calling app to make and receive calls within HubSpot."

> "**When using an integrated calling app, you'll no longer be using calling minutes from your HubSpot account.**"

Source: https://knowledge.hubspot.com/calling/manage-phone-numbers-registered-for-calling

> "You can integrate a third-party calling provider from the App Marketplace so your team can place and log calls in
> HubSpot while using **your existing telephony system**."

DOCUMENTED — the SDK is telemetry, not call origination. In the Calling Extensions SDK, `outgoingCall()` and
`incomingCall()` merely *notify* HubSpot that a call has started so it can create an engagement:
Source: https://developers.hubspot.com/docs/guides/api/crm/extensions/calling-sdk

> "outgoingCall — Sends a message to notify HubSpot that an outgoing call has started."
> "incomingCall — Sends a message to notify HubSpot that an incoming call has started."
> `fromNumber` — "The caller's number in E.164 format (e.g., +15551234567)."
> `toNumber` — "The recipient's phone number in E.164 format."

`fromNumber` is a **reported** value used for CRM logging and for `onCallerIdMatchSucceeded` / `onCallerIdMatchFailed`
(which match an *inbound* number against CRM contact/company records). It is **not** a field that sets the CLI on the
wire. The SDK exposes no CLI-selection or CLI-authorization surface at all.

**Therefore (synthesis):** with Aircall/Ringover/Kixie, the caller ID is a number owned by *that provider* (or ported to
them), and the carrier relationship, numbering-authority registration, and CLI-spoofing liability sit with *that
provider*, not HubSpot and not Twilio-via-HubSpot. HubSpot corroborates the practical consequence:

> "it is recommended to use one of HubSpot's calling partner integrations. **This will involve acquiring a new number to
> place calls** but should resolve any remaining caller ID issues." (FAQ)

NOT DOCUMENTED by HubSpot: per-provider caller ID rules, whether any specific partner supports presenting a
customer-owned Spanish CLI, or any partner's CNMC status. That has to be researched per provider.

---

## Q7 — Does HubSpot document Spanish regulation / 2025 Spanish caller ID rules?

**DOCUMENTED — YES. Contrary to the "likely none" expectation, HubSpot documents it explicitly and cites the primary
source.**

On https://knowledge.hubspot.com/calling/what-countries-are-supported-by-calling HubSpot names:
- the regulator: "The Ministry for Digital Transformation (Spain's regulatory authority for electronic communications)"
- the instrument: **Order TDF/149/2025**
- with a direct BOE deep link: https://www.boe.es/buscar/act.php?id=BOE-A-2025-2870
- effective framing: "As of June 2025"
- the two substantive prohibitions: (i) mobile prefixes 346/347 barred for B2C telemarketing/customer service;
  (ii) mandatory blocking of calls falsely presenting a Spanish CLI from international origin.

This is a SaaS vendor with a Twilio relationship publicly conceding the rule is operative and that it breaks their
own-number feature. That is strong evidence of real enforcement, not paper regulation.

NOT DOCUMENTED anywhere in HubSpot's KB: Lista Robinson, LOPDGDD, CNMC alias registry, the €2M sanction ceiling,
calling-hours restrictions, or guidance on which Spanish numbering (900/800/geographic) to adopt. HubSpot only documents
the CLI/numbering blocking consequence.

Third-party (NON-HubSpot, corroborating the regulation's substance — cite separately, lower authority):
- https://www.bakertilly.es/en/insights/new-regulation-on-business-communications-and-telephone-fraud — "Since June 7,
  2025 …"; Art. 9 prohibits mobile numbers for unsolicited commercial calls/customer service; Art. 4 blocking of empty/
  unassigned CLI; **Art. 5 requires blocking of international calls that falsely appear to originate from Spanish
  numbers, except roaming**; Art. 8 CNMC alias registry.
- https://glofera.com/en/banning-commercial-calls-how-to-adapt/ — timeline: BOE publication Feb 15 2025; blocking of
  irregular numbering from Mar 7 2025; **Jun 7 2025** mobile-prefix restriction; Jun 7 2026 messaging/alias measures.

Note the exact alignment: Spanish Art. 5 (block international calls faking Spanish CLI) is precisely the mechanism that
kills HubSpot's verified-CLI model, because HubSpot/Twilio traffic originates internationally relative to Spanish
operators.

---

## Reconciling the user's report ("it worked, including caller ID")

Explanations consistent with the documentation — cannot be resolved without knowing what they actually configured:

1. **They used a HubSpot-provided Spanish number, not a registered own-number.** Spain is offered as "(local)". A
   Twilio-owned +34 geographic number is legitimately originated and is *not* covered by the failure clause. This is the
   most likely explanation and it is NOT the same capability as "my own number as caller ID."
2. **They used Twilio Connect or a third-party partner**, where the number is provider-owned.
2b. **They ported their existing Spanish geographic number into HubSpot.** This would genuinely feel like "my own number
   worked as caller ID" from the user's point of view, while technically being a HubSpot/Twilio-owned number. Worth
   ruling out explicitly, because it is the single most likely way a user honestly reports "it worked, including caller
   ID" in Spain post-June-2025.
3. **Timing.** HubSpot's Spain note is "As of June 2025" and the page's last-updated date is June 23, 2026. A test before
   HubSpot/Twilio implemented the block could have succeeded.
4. **The callee wasn't behind a Spanish operator**, or the call wasn't B2C. The blocking rule is enforced by Spanish
   operators on inbound-to-Spain traffic.
5. **HubSpot hedges with "may."** Enforcement may be inconsistent across Spanish operators.

**The question to put to the user:** in Settings → Calling, was the number listed under *"Get a HubSpot number" /
HubSpot-provided phone numbers*, or **ported in**, or under *"Add phone number" / outbound (registered) phone numbers*?
And was the CLI a +34 6/7 mobile or a +34 9 geographic? Those two answers fully disambiguate, and they point to opposite
conclusions.

**Load-bearing warning for whatever you are building:** do not treat "HubSpot does this at scale in Spain" as evidence
that verified-CLI / own-number presentation is enforceable-in-practice. HubSpot's documentation says the opposite. What
HubSpot actually does at scale in Spain is **carrier-owned geographic numbering** (provisioned or ported), which is the
compliant path, not the permissive one. The evidence points toward Spanish enforcement being real and network-level, not
paper.

---

## Sources actually fetched

HubSpot Knowledge Base:
1. https://knowledge.hubspot.com/calling/register-an-outbound-phone-number — "Register an outbound phone number" (upd. May 14, 2026)
2. https://knowledge.hubspot.com/calling/manage-phone-numbers-registered-for-calling — "Set up calling" (upd. Apr 14, 2026)
3. https://knowledge.hubspot.com/calling/what-countries-are-supported-by-calling — "Supported countries for HubSpot calling" (upd. Jun 23, 2026)
4. https://knowledge.hubspot.com/calling/acquire-and-validate-hubspot-provided-phone-numbers — (upd. Aug 5, 2026)
5. https://knowledge.hubspot.com/calling/set-up-number-verification-to-improve-call-trust-and-deliverability — (upd. Jun 22, 2026)
6. https://knowledge.hubspot.com/calling/calling-frequently-asked-questions — "Calling | FAQ" (upd. Aug 14, 2026)
7. https://knowledge.hubspot.com/calling/integrate-a-third-party-calling-provider-with-hubspot — (upd. Jan 30, 2026)
7b. https://knowledge.hubspot.com/calling/port-out-a-hubspot-phone-number — "Port a number to HubSpot" (upd. Jul 30, 2026)

Note: https://knowledge.hubspot.com/calling/port-your-phone-number-to-hubspot returns **404** — the live porting URL is
the /port-out-a-hubspot-phone-number slug above despite its misleading name.

HubSpot Developer Docs:
8. https://developers.hubspot.com/docs/guides/api/crm/extensions/calling-sdk — Calling Extensions SDK

HubSpot pages seen via search excerpt only (NOT fully fetched — treat quotes as indicative):
9. https://knowledge.hubspot.com/calling/hubspot-calling-minutes — "Set up a Twilio Connect account in HubSpot"
10. https://knowledge.hubspot.com/calling/what-are-the-technical-requirements-to-use-the-calling-tool
11. https://knowledge.hubspot.com/calling/configure-call-routing-work-hours-and-voicemail
12. https://community.hubspot.com/t/troubleshooting-error-adding-your-phone-number-to-twillio-connect/20277 — community, low authority

Primary regulation:
13. https://www.boe.es/buscar/act.php?id=BOE-A-2025-2870 — Order TDF/149/2025 (link as cited by HubSpot; I did not fetch the BOE text itself)

Third-party corroboration of the Spanish rules (non-HubSpot):
14. https://www.bakertilly.es/en/insights/new-regulation-on-business-communications-and-telephone-fraud
15. https://glofera.com/en/banning-commercial-calls-how-to-adapt/

## Explicit NOT DOCUMENTED list
- A HubSpot "known issues" page for calling — none found.
- HubSpot calling settings **API** for managing registered outbound numbers / caller ID (the Calling Extensions API covers
  app registration and call logging, not CLI provisioning) — NOT DOCUMENTED.
- Any documented way to present a customer-owned Spanish CLI compliantly via HubSpot native calling — NOT DOCUMENTED.
- STIR/SHAKEN or attestation equivalent for non-US numbers — explicitly stated as US-only.
- Whether Spain HubSpot-provided numbers require a local Spanish address for the Twilio regulatory bundle (page says
  "some country regulations vary on whether or not they require a local address" but gives no per-country detail) — NOT DOCUMENTED.
- Downstream Spanish carrier behind Twilio — NOT DOCUMENTED.
