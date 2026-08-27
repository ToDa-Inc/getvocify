# Twilio assumption audit

Audit date: 2026-08-27. Market: Spain (+34). Design under test: SDRs verify their **own** existing
phone number via Twilio Outgoing Caller IDs; no Twilio numbers purchased; that number is presented
as caller ID on outbound sales calls to Spanish destinations.

**Headline:** A1 is DOCS SILENT (and the "US-only" folklore is unsubstantiated), but A3 and A4
independently refute the *product*. Spanish law mandates carrier blocking of the exact call this
architecture places. The BYO-caller-ID design is not viable in Spain regardless of whether Twilio's
verification flow works.

---

## A1 — "Twilio's Outgoing Caller ID verification works for non-US numbers, including Spanish +34 mobiles and landlines."

**Verdict:** DOCS SILENT (no documented country restriction; no documented statement of
international support either). The specific "Verified Caller ID is US-only" claim is
**unsubstantiated** — I could not find it in any Twilio primary source.

**Primary source:** <https://www.twilio.com/docs/voice/api/outgoing-caller-ids> and
<https://www.twilio.com/docs/voice/api/verifying-caller-ids-scale>

Neither page contains a country allowlist, a country blocklist, a "United States only" statement,
or any geographic qualifier on the feature. The `PhoneNumber` parameter is documented in generic
international terms:

> "The phone number to verify. Should be formatted with a '+' and country code for example,
> +16175551212 (E.164 format). Twilio will also accept unformatted US numbers for example,
> (415) 555-1212 or 415-555-1212."

The US-specific text there is a *convenience* affordance for unformatted input, not a restriction.
E.164 with country code is the documented primary format.

**Confirmed sub-claims (both true, from `verifying-caller-ids-scale`):**

> "Twilio will then call that phone number on the PSTN, with a caller ID of +14157234000."

> "The verification call is in English. Other languages aren't supported."

So: origin `+14157234000` — CONFIRMED. English-only — CONFIRMED. A Spanish SDR hears an English
robot read a code. That is a real onboarding-friction and support-ticket cost, not a blocker.

**On the community failure reports (StackOverflow 77477987):** the question is from a **trial
account** verifying Ukrainian and Spanish numbers. Two documented mechanisms explain the failure
without any US-only rule:

1. **Voice Dialing Geographic Permissions.** The verification call is an ordinary Twilio outbound
   PSTN call, so it is subject to Geo Permissions. If ES is not enabled — or if the SDR's number
   falls in a range Twilio classifies High-Risk — the call is never placed.
   <https://www.twilio.com/docs/sip-trunking/voice-dialing-geographic-permissions> ("Geographic
   Permissions apply to both Programmable Voice and Elastic SIP Trunking"), error
   <https://www.twilio.com/docs/api/errors/21215> ("You attempted to initiate an outbound phone
   call to a phone number that is not enabled on your account"). Note per the Geo Permissions doc,
   **mobile ranges are frequently the High-Risk category** — which is exactly what SDR personal
   mobiles are.
2. **Trial-account cap of 5 verified numbers.**
   <https://www.twilio.com/docs/usage/trials/try-out-voice.md> — "Each account can verify up to
   five numbers."

The accepted answer on that StackOverflow question also points at Geo Permissions. The "US only"
answer is from a 31-reputation account, cites no Twilio source, and links to a help-center article
that does not say it. **Treat it as folklore, not as evidence.**

**What this means for a BYO-caller-ID design:** A1 is *not* the thing that kills you. Silence plus
explicable community failures is a moderate operational risk (English-only prompt, Geo Permissions
must be enabled for ES including High-Risk mobile ranges, per-number verification support burden),
not an architectural one. Do not spend your remediation budget here — spend it on A3/A4.

**Test that would settle it:** On an **upgraded** (non-trial) account, enable ES Geo Permissions
for both Low-Risk and High-Risk ranges, then `POST /OutgoingCallerIds` for (a) a +34 6xx mobile,
(b) a +34 7xx mobile, (c) a +34 91x/93x geographic landline. Record HTTP status, the returned
`ValidationCode`, the `CallSid`, and the terminal call status / `HangupCauseCode` for each
verification call. Repeat with High-Risk disabled to isolate the Geo Permissions variable. Ten
minutes of work; settles A1 definitively.

---

## A2 — "Transit Caller ID is being sunset, and Verified Caller ID is the sanctioned replacement."

**Verdict:** SUBSTANCE CONFIRMED — **DATE AND RULE REFUTED.** The date you shipped against is
wrong, and the "hard rejection" framing is not supported by any Twilio primary source.

**Primary source:** <https://www.twilio.com/en-us/changelog/action-required--transit-caller-id-sunset-migrate>
(Twilio Changelog, dated **Apr. 13, 2026**). Title: "Transit Caller ID Sunset: Migrate to Verified
Caller ID or Immutable Call Forwarding Before **June 22, 2026**".

> "Starting June 22, 2026, Twilio will begin sunsetting the Transit Caller ID feature **for some
> customers**. Customers currently using Transit Caller ID to present a different phone number than
> the one they're calling from will need to migrate to an alternative before this date."

> "**Static non-Twilio numbers:** Customers who always present the same caller ID on every call
> should migrate to Verified Caller ID or Twilio-owned numbers in their Twilio account."

> "Customers who have not migrated by June 22, 2026 **may experience interruptions** to their voice
> flows."

Rationale Twilio gives:

> "Globally, regulators are increasingly restricting calls with modified caller IDs. Several
> countries have already implemented blocking or restrictions, and additional markets are
> following."

**Three corrections to the claim as you stated it:**

1. **The date is June 22, 2026, not May 31, 2026.** The May 31 date appears only in the third-party
   dev.to article ("Twilio's Transit CallerID Sunset on May 31"). It is not in Twilio's changelog.
   The dev.to piece is dated May 8 — i.e. it was published *after* Twilio's own April 13 changelog
   announcing June 22, and contradicts it. **The dev.to article is wrong and should not be cited
   internally.**
2. **This date has already passed.** Today is 2026-08-27. If any part of your stack was relying on
   Transit Caller ID, it is already past the migration deadline — this is not a future planning
   item, it is a present-tense production exposure. Go read your call logs.
3. **No Twilio primary source states the exact three-option rejection rule** ("Twilio will reject
   outbound calls whose caller ID is not (a) Twilio-owned, (b) Verified, or (c) via ICF/CallTokens").
   Twilio's own language is hedged: "begin sunsetting… for some customers", "may experience
   interruptions". The crisp rule is the dev.to author's synthesis. **UNVERIFIABLE FROM PUBLIC DOCS
   as an exact rule.**

**However**, Twilio *does* state the rejection principle in a separate primary source —
<https://www.twilio.com/en-us/changelog/elastic-sip-trunking---immutable-call-forwarding-with-calltoken->
(Twilio Changelog, Jun. 23, 2026):

> "Twilio will currently reject these forwarded calls since they are from a non-Twilio or Verified
> caller ID number without the new Immutable Call Forwarding feature."

That is Twilio confirming, in its own words, that non-Twilio / non-Verified caller IDs get rejected.
So the *direction* of A2 is right: **Verified Caller ID is genuinely the sanctioned path for a
static BYO number.** Your architecture is on the correct side of this particular change.

**What "Immutable Call Forwarding" and "CallTokens" are (and why they don't help you):**

Source: <https://www.twilio.com/docs/voice/trusted-calling-with-shakenstir>

A `CallToken` is a token Twilio puts in the inbound-call webhook body containing the SHAKEN/STIR and
DIV (diversion) PASSporTs from the incoming SIP headers. To forward a call while preserving the
original caller's ID, you pass that `CallToken` back as a parameter when creating the new Call
Resource, with the original caller's number as `From`. Twilio validates that the caller ID matches
the token:

> "Twilio will use the `CallToken` in the outgoing leg to verify the CallerID. If the CallerID
> doesn't match the `CallToken`, Twilio will reject the call with an error."

Immutable Call Forwarding is the same mechanism packaged for Elastic SIP Trunking, via the
`X-Twilio-CallToken` SIP header, currently public beta.

**Critically: ICF/CallTokens require a real inbound leg to forward.** They are a call-*forwarding*
mechanism, not a way to assert an arbitrary caller ID on a fresh outbound call. **Outbound
click-to-call has no inbound leg**, so ICF is structurally unavailable to you. Your only two
sanctioned options are Verified Caller ID or a Twilio-owned number. Do not put ICF on the roadmap as
an escape hatch for A3/A4 — it is not one.

**What this means for a BYO-caller-ID design:** A2 does not invalidate the architecture; it
validates the *choice* of Verified Caller ID over Transit. But fix the date in every internal doc,
and audit production now for calls that were silently relying on Transit behaviour before June 22.

**Test that would settle it:** Query your own Voice logs for the window 2026-06-15 → today,
grouped by day and destination country, counting calls with `HangupSource` / `HangupCauseCode`
indicating Twilio-side rejection, split by whether the `From` was a Twilio-owned number vs a
Verified Caller ID vs neither. A step change at June 22 tells you whether you had Transit exposure.
Separately, ask your Twilio account team in writing whether your account SID was in the "some
customers" cohort — that is the only way to resolve Twilio's deliberate vagueness.

---

## A3 — "A Twilio account does not need to be registered in Spain to present a Spanish verified caller ID."

**Verdict:** CONFIRMED on the narrow KYC point — **but this is the wrong question, and the answer is
misleading in context. The design is blocked by A3's second half.**

**Primary source 1 (the KYC distinction you asked about):**
<https://www.twilio.com/en-us/guidelines/es/regulatory> — Spain regulatory guidelines. To
**purchase** a Spanish local number, Twilio requires Name + proof of identity, a Spanish fiscal ID
(DNI/NIF/NIE, or CIF for businesses) + proof, and an Address "**Must be within locality or region
covered by the phone number's prefix**; a PO Box is not acceptable". For Spanish Mobile / National /
Toll-Free the address "Must be within Spain". Also: "*Spain national numbers are prohibited from
being used by ISVs/number resellers.*"

Corroborated by <https://www.twilio.com/docs/numbers-and-senders/phone-number-senders>: "Before you
can use a non-US phone number, you must submit a compliance registration **before buying and
provisioning the number**."

That regulatory-bundle machinery is scoped to *purchase*. The `OutgoingCallerIds` resource has no
bundle requirement documented anywhere. **So yes: no NIF, no Spanish address, no Spanish entity is
needed to add a +34 Verified Caller ID.** Assumption confirmed as literally stated.

**Primary source 2 (the part that matters):**
<https://www.twilio.com/en-us/guidelines/es/voice> — Spain voice guidelines. The row labelled
"**Outbound requirements** — *Conditions that must be met before outbound calls are allowed from
Twilio to non-Twilio numbers in this locale*" reads:

> "For domestic calls, please use a Twilio phone number."

**Precise interpretation, as requested.** This is stronger than a recommendation and weaker than a
Twilio-side technical block:

- It is **not** a "Best practice". That is a *separate row* on the same table, and for Spain it
  reads "N/A". Twilio deliberately placed this line under **requirements**, whose own column
  definition is "*Conditions that must be met before outbound calls are allowed*". Twilio is
  telling you this is a precondition, not advice.
- It is **not** documented as a Twilio API-level rejection. Nothing says `POST /Calls` will 400. The
  polite "please use" phrasing suggests Twilio is not enforcing it at its own edge.
- It **is** a compliance requirement enforced *downstream, by Spanish carriers, by law* — see A4.
  The blocking is real and mandatory; it just happens at the Spanish interconnect rather than in
  Twilio's API.

The mechanism: your call originates on Twilio's international infrastructure and arrives in Spain
through an international interconnect carrying a +34 CLI. **Orden TDF/149/2025 Art. 5.1 obliges the
receiving Spanish operator to block exactly that call.** Twilio's one-line "requirement" is the
compressed, non-legal-advice version of that statute. Read it as: *a +34 caller ID only survives
into Spain if the call also originates inside Spain, which for Twilio means a Twilio-provisioned
Spanish number.*

**What this means for a BYO-caller-ID design:** The absence of a KYC gate on Verified Caller ID is a
false green light. You can successfully register a +34 Verified Caller ID, get a `200 OK`, see it in
the Console, place the call, get a `CallSid`, be billed — and have the call blocked at the Spanish
border. **Your happy path is indistinguishable from your failure path at the Twilio API layer.**
That is the worst possible failure mode for a cost model, because nothing in your own telemetry
tells you it's broken; you just get low answer rates that look like bad lists or bad SDRs.

**Test that would settle it:** Place matched-pair test calls to a Spanish mobile you control on a
major Spanish MNO (Movistar/Vodafone/Orange) and on at least one MVNO: (a) `From` = +34 Verified
Caller ID you own, (b) `From` = Twilio-provisioned +34 number, (c) `From` = a non-Spanish Twilio
number. For each, record whether the handset rings, what CLI is displayed (present / withheld /
replaced / marked unverified), and Twilio's `HangupCauseCode`. Per Art. 5.2 the operator may either
block outright *or* suppress/flag the CLI, so **check the handset display, not just connection
success** — a connected call with a suppressed CLI still destroys the entire product pitch. Also
test from a Spanish mobile actually roaming abroad, since roaming is the one statutory exemption.

---

## A4 — "Spanish mobile numbers as caller ID are restricted for commercial calls (Orden TDF/149/2025)."

**Verdict:** CONFIRMED, and **materially worse than the assumption as stated.** Two independent
articles of the same Order each kill the design, and neither has an ownership exception.

**Primary source:** Orden TDF/149/2025, de 12 de febrero. BOE núm. 40, 15/02/2025.
BOE-A-2025-2870. Consolidated text: <https://www.boe.es/eli/es/o/2025/02/12/tdf149/con>
PDF: <https://boe.es/boe/dias/2025/02/15/pdfs/BOE-A-2025-2870.pdf>
Entry into force: 07/03/2025.

### Art. 9 — mobile numbering banned for this call type

> "**Artículo 9. Prohibición de utilización de la numeración móvil para llamadas de atención al
> cliente o para la realización de llamadas comerciales no solicitadas.**
> 1. Se prohíbe la utilización de rangos de numeración atribuidos al servicio de comunicaciones
> móviles para la prestación de servicios de atención al cliente y para la realización de llamadas
> comerciales no solicitadas.
> 2. El incumplimiento de la prohibición establecida en el apartado 1 será sancionado conforme a lo
> establecido en el artículo 107.19 de la Ley 11/2022, de 28 de junio, General de
> Telecomunicaciones."

### Art. 5 — Spanish CLI from abroad must be blocked

> "**Artículo 5. Bloqueo de llamadas con origen internacional identificadas por un CLI del plan
> nacional de numeración fija o móvil.**
> 1. Deberán bloquearse las llamadas de servicios de comunicación vocal, recibidas desde el
> extranjero cuando presenten como CLI un número de teléfono español, **salvo que se trate de un
> caso de itinerancia internacional**."

### Art. 10 — what is permitted instead

> "1. Se atribuye los segmentos N=8 y 9, para el valor cero de las cifras X e Y, del plan nacional
> de numeración telefónica, además de a los servicios de cobro revertido automático, a los
> servicios de atención a clientes y a la realización de llamadas comerciales no solicitadas."

### Answers to your specific questions

**Which prefixes are restricted?** Art. 9 is not written as a prefix list — it restricts "*rangos de
numeración atribuidos al servicio de comunicaciones móviles*", i.e. whatever CNMC has attributed to
mobile service. In practice that is the **6xx and 7xx** ranges. Disposición final segunda amends the
2013 mobile-range attribution resolution to align with this. Separately, Twilio's Spain voice page
notes "Outbound calls from a number with the **+34902** prefix are not allowed."

**Which call types?** **Both** — the article covers "*servicios de atención al cliente*" (customer
service) **and** "*llamadas comerciales no solicitadas*" (unsolicited commercial calls). Outbound
SDR prospecting is squarely the second. There is no "warm lead" or "opted-in" carve-out in Art. 9
itself. Do not let anyone argue their way out of this on call-type grounds.

**Does it apply to calls originating outside Spain?** Art. 9 binds the *caller* regardless of where
the call originates — Art. 2.3 scopes Chapter IV to "*los prestadores de servicios de atención al
cliente o a quienes realizan llamadas comerciales no solicitadas*", i.e. **you and your customers**,
not just carriers. And Art. 5.1 independently mandates blocking of *any* +34 CLI arriving from
abroad. Art. 4.5 makes the parallel point explicitly for Art. 4: "*Este artículo se aplica
independientemente de si la llamada se realiza dentro de España o entra en España desde el
extranjero a través de una interfaz internacional de interconexión.*" Per Art. 2.2, the entity
obliged to block under Art. 5 is "*el operador que recibe la llamada por una interfaz internacional
de interconexión*" — the Spanish carrier receiving your Twilio traffic. You cannot route around
this; the blocking party is on the far side.

**Does it apply when the caller OWNS the number?** **Yes. There is no ownership exception in either
article.** This is the single most important finding for your design. Art. 9 prohibits a *use* of a
*range*, not a spoofing act — legitimate ownership is irrelevant. Art. 5.1's only exemption is
"*itinerancia internacional*" (international roaming), meaning a physical handset roaming abroad on
a real roaming agreement. A cloud PBX asserting a +34 CLI is definitionally not roaming, and Art.
5.4 requires international calls to arrive on circuits "*claramente diferenciados*" from national
ones, so the traffic is structurally identifiable as foreign-originated. **"But the SDR really does
own that mobile" is not a defence under either article.**

**What number types remain permitted?** Spanish **geographic/landline** numbering (91, 93, …),
**800/900** ranges (Art. 10, free to the caller, and Art. 10.3 generally authorises 800/900 in the
CLI field), and specially-attributed short numbers. Note that even a permitted *number type* still
has to satisfy Art. 5.1 — so it must originate from inside Spain, i.e. be a Twilio-provisioned
Spanish number, not a BYO verified one.

**Effective dates.** Disposición final tercera: the Order entered into force 07/03/2025; Art. 5.1
had to be complied with "*en el plazo máximo de tres meses desde su entrada en vigor*" and Art. 9
"*producirán efectos a los tres meses de su entrada en vigor*" — both **07/06/2025**. Confirmed by
Twilio's own Spain voice guidelines: "**Spanish mobile numbers can't be used for unsolicited
marketing or customer service calls.**"

**Quantifying "how much of a problem" personal mobiles are — bluntly: total.** This is not a
degradation, a deliverability tax, or an answer-rate haircut you can optimise. It is:

1. **Illegal** for your customers under Art. 9, sanctionable under Art. 107.19 Ley 11/2022 — and
   the sanctioned party is *your customer*, whom you sold this to.
2. **Technically blocked** under Art. 5.1 by mandatory obligation on the receiving Spanish carrier,
   with no ownership and no BYO exception.
3. **In force for ~14 months already** (since 2025-06-07).

Both failure modes stack. Even if you moved every SDR from a personal mobile to a Spanish
*geographic landline* they personally own — fixing Art. 9 — Art. 5.1 still blocks it, because the
call still arrives from abroad with a +34 CLI. **BYO caller ID cannot be made compliant in Spain by
changing which number the SDR verifies.** The only compliant configuration is Twilio-provisioned
Spanish geographic or 800/900 numbering, which requires the NIF/DNI + local-address regulatory
bundle from A3 — precisely the cost and onboarding friction the architecture was designed to avoid.

**Test that would settle it:** The A3 matched-pair test above already settles the technical half.
For the legal half, do not test — get written Spanish telecoms-counsel advice on Art. 9 exposure for
(a) your customers as "*quienes realizan llamadas comerciales no solicitadas*" and (b) you as the
platform enabling it. Also request CNMC/SETID confirmation of whether any Art. 5.3 or Art. 4.6
exception has been published covering cloud-PBX BYO-CLI scenarios — those articles do permit
published exceptions by SETID resolution, and that is the only legitimate path by which this design
could become viable. Check the SETID portal before assuming there is none.

---

## A5 — "Dual-channel recording bills at 1x per minute, not 2x."

**Verdict:** CONFIRMED for recording generation; CONFIRMED for storage as of 2022.

**Primary source 1:** <https://www.twilio.com/en-us/voice/pricing/us> — "Call recording | Recording
**$0.0025 / min** | Storage **$0.0005 / min per mo** | Transcription $0.0500 / min". A single
recording rate; no dual-channel line item, no multiplier.

**Primary source 2:** <https://www.twilio.com/en-us/blog/announcing-dual-channel-call-recordings-by-default>
(Twilio blog, May 25, 2022):

> "voice recordings are now recorded and stored at Twilio in dual-channel by default **at no
> additional cost**"

> "As part of this release, **dual-channel is now the same price as mono-channel storage** because
> we want all of our voice customers to benefit from dual-channel recordings."

**Caveat worth knowing:** an older Twilio blog
(<https://www.twilio.com/en-us/blog/products/launches/more-accurate-call-transcriptions-available-now-html>)
states "Storage of dual-channel recordings is $0.001 per minute (double the price of mono recording
because the file is twice the size)." That is **superseded** by the 2022 announcement above. If
anyone cites the 2x storage figure, they are reading a stale page. Generation was always 1x
($0.0025/min, "the same as standard mono recording") even in that older post.

**Also relevant to your cost model:** storage is billed on *rounded-up* minutes per recording —
<https://help.twilio.com/articles/223132527-How-much-does-it-cost-to-record-a-call>: "Recording
storage costs are calculated by rounding the duration of each recording up to the next minute. For
example, three recordings of five seconds each will count together as three minutes, not 15
seconds." For SDR dialling — high volume, many very short calls (no-answers, instant hangups) — this
rounding can dominate your storage line. First 10,000 stored minutes per parent account are free.

**What this means for a BYO-caller-ID design:** No impact on the caller-ID architecture. Your 1x
assumption is safe. Fix the rounding assumption if you modelled storage on actual seconds.

**Test that would settle it:** Record one 30-second dual-channel call and one 30-second mono call on
the same account, then pull the `usage/records` API filtered to `calls-recordings` and
`recordings-storage` for that day and compare per-recording charges. Settles it from your own
invoice rather than from a marketing page.

---

## A6 — "There is no practical cap on the number of Verified Caller IDs per Twilio account."

**Verdict:** DOCS SILENT for upgraded accounts. A hard documented cap exists for **trial** accounts.

**Primary source (trial cap):** <https://www.twilio.com/docs/usage/trials/try-out-voice.md>

> "Each account can verify up to five numbers."

> "If you have multiple accounts, you can use the same verified number for up to three accounts,
> including subaccounts. If you sign up for a fourth Twilio account with the same number, your
> number is not added as a verified number."

**Primary source (cap lifted on upgrade):**
<https://www.twilio.com/docs/sip-trunking/scale-and-limits> — "Note: Trial accounts may only place
calls TO and FROM verified numbers… **This restriction is removed once you upgrade your account.**"
That same page enumerates explicit account maxima (100 SIP trunks, 1 termination CPS, etc.) and
**does not list any OutgoingCallerIds limit** — a meaningful omission on the page whose entire
purpose is documenting scale limits.

The `OutgoingCallerIds` resource docs (<https://www.twilio.com/docs/voice/api/outgoing-caller-ids>)
document a paginated list endpoint with no stated maximum. The `limit` / `page_size` parameters in
the SDKs are client-side pagination controls, not account caps — don't let anyone misread those as
a documented limit.

**Two undocumented risks you should treat as real:**

1. **No published upgraded-account cap** means no *committed* cap. Twilio can introduce one, or
   apply an unpublished internal throttle, without a changelog entry.
2. **The 3-account reuse rule is documented only for trial accounts.** Whether an analogous rule
   applies to verified caller IDs across upgraded accounts and subaccounts is **UNVERIFIABLE FROM
   PUBLIC DOCS** — and it matters a lot for a multi-tenant design, because two of your customers
   could plausibly try to verify the same shared office landline, and an SDR changing employers
   would need their number verified on a second tenant.

**What this means for a BYO-caller-ID design:** Moot for Spain given A3/A4, but if you take this
architecture to a market where it *is* legal, an undocumented cap plus an undocumented cross-account
reuse rule is a genuine scaling risk on a per-SDR-verification model. Also note verification is
one-time with no re-challenge mechanism, so carrier/ownership changes silently leave stale verified
entries on your account — a compliance liability of its own.

**Test that would settle it:** Script `POST /OutgoingCallerIds` against an upgraded sandbox account
until it errors, logging the error code and the count at failure — but note you cannot complete
verification without answering each call, so use a Twilio number with a TwiML `<Play digits="…">`
webhook keyed off the `+14157234000` caller (the pattern documented in
`verifying-caller-ids-scale`) to auto-answer. Separately, verify one number on two upgraded accounts
and then a third to probe for a reuse rule. Then get the cap and the reuse rule **in writing** from
your Twilio account team — an undocumented limit you've only probed empirically is not a limit you
can plan capacity against.

---

## A7 — "Twilio's webhook signature validation depends on the exact request URL."

**Verdict:** CONFIRMED. Rebuilding the URL from a configured public base URL is the correct approach
behind a proxy — with several documented gotchas that will bite you.

**Primary source:** <https://www.twilio.com/docs/usage/security>

> "Twilio assembles its request to your application, including the final URL and any `POST` fields.
> If your request is a `POST`, Twilio takes all the `POST` fields, sorts them alphabetically by
> their name, and concatenates the parameter name and value to the end of the URL (with no
> delimiter). **Only query parameters get parsed to generate a security token, not the `POST`
> body.** If the request is a `GET`, the final URL includes all of the Twilio request parameters
> appended in the query string of your original URL using the standard delimiter `&`…"

> "Twilio takes the resulting string (**the full URL with the scheme, port, query string** and any
> `POST` parameters) and signs it using HMAC-SHA1 and your AuthToken as the key."

> "Take the full URL of the request URL you specify for your phone number or app, **from the
> protocol (https…) through the end of the query string (everything after the ?)**."

So the signature covers scheme, host, port, path, **and** query string. A proxy that rewrites *any*
of those breaks validation. Reconstructing from a configured public base URL is exactly right —
that is the only way to recover the URL Twilio actually signed.

**Documented gotchas, all from the same page:**

- **Query strings are signed.** You must preserve them byte-for-byte, in the original order. Do not
  re-serialise, re-sort, or URL-re-encode them when rebuilding.
- **JSON bodies use `bodySHA256`.** "If the `Content-Type` is `application-json`, don't use the JSON
  body to fill in the `validator`'s parameter for `POST` parameters. The query parameter
  `bodySHA256` will be included in the request." Use the `validateRequestWithBody` variant. The
  docs' own example URL is
  `https://example.com/myapp?bodySHA256=5ccde7145dfb8f56479710896586cb9d5911809d83afbe34627818790db0aec9`
  — note `bodySHA256` arrives **as a query parameter**, so your rebuilt URL must include it.
- **Scheme changes the port rule.** The docs state that for some schemes Twilio "will *keep* the
  port (if any) in the URL when computing the signature" and for others "will also *drop* the port".
  A TLS-terminating proxy is the classic trap: if Twilio signed `https://host/path` (443 implicit)
  and your app sees `http://host:8080/path`, validation fails. Your configured base URL must carry
  the scheme and port exactly as Twilio was configured with — including whether a default port is
  written explicitly.
- **Credentials are always stripped.** "Twilio will *drop* the username and password (if any) from
  the URL before computing the signature." If you use HTTP Basic auth on webhook URLs, don't include
  credentials in your rebuilt base URL.
- **Trailing-slash / index rewrites.** "…then Apache or PHP may rewrite that URL so it has a
  trailing slash… you could end up with an incorrect hash, because Twilio built the hash using
  `https://example.com/twilio` and you may have built the hash using `https://example.com/twilio/`."
- **Whitespace trimming middleware.** "Some frameworks may trim whitespace from `POST` body fields.
  A notable example is Laravel, which has the TrimStrings middleware turned on by default… **Certain
  Node.js middleware may also trim whitespace from requests.**" Relevant to your stack.
- **WebSocket handshakes** (Media Streams): "try appending a trailing `/` character to the URL that
  you pass to the signature validation method."
- **Use the SDK, not hand-rolled HMAC.** "We highly recommend you use the SDKs to do signature
  validation," and of the worked manual example: "This example is for illustrative purposes only.
  When validating requests in your application, only use the provided helper methods."

**On "parameter sets changing without notice":** Twilio's page does not carry an explicit warning
that webhook parameter sets may change. However, because the signature is computed over *all* POST
fields, a signature-validating implementation is inherently forward-compatible — new parameters are
included in Twilio's hash and in yours automatically, provided you pass the **full** parameter map
to the validator rather than an allowlisted subset. **Do not filter or allowlist parameters before
validating.** Note also that A2's ICF section mentions Twilio "may send additional webhook parameter
`StirPassportToken`" — a live example of the parameter set growing.

**What this means for a BYO-caller-ID design:** No caller-ID implications. Your approach is correct.
Verify your configured base URL includes the exact scheme and the port exactly as Twilio has it
configured, that you forward query strings unmodified, and that no body-trimming middleware runs
before validation.

**Test that would settle it:** Twilio publishes a signature test endpoint — see the "Test the
validity of your webhook signature" section of the security page. Beyond that, add a startup
assertion comparing your configured public base URL against the webhook URL actually registered on
the Twilio number/app via the API, and fail loudly on mismatch — that turns a silent
403-in-production into a deploy-time error. Then run one form-encoded and one JSON webhook through
the real proxy path in staging and confirm both validate.

---

## Bottom line

| # | Assumption | Verdict |
|---|---|---|
| A1 | Verified Caller ID works for +34 | DOCS SILENT — "US-only" claim unsubstantiated; real risk is Geo Permissions + English-only prompt |
| A2 | Transit sunset, Verified is replacement | Substance CONFIRMED; **date REFUTED** (Jun 22 2026, already passed); hard rule UNVERIFIABLE |
| A3 | No Spanish registration needed | CONFIRMED narrowly, but "use a Twilio phone number" is a **requirement**, not advice |
| A4 | +34 mobiles restricted for commercial calls | **CONFIRMED and worse** — Art. 9 bans the use, Art. 5.1 blocks the call, no ownership exception |
| A5 | Dual-channel recording 1x | CONFIRMED (watch storage minute rounding) |
| A6 | No cap on Verified Caller IDs | DOCS SILENT for upgraded accounts (trial = 5); cross-account reuse rule UNVERIFIABLE |
| A7 | Signature validation depends on exact URL | CONFIRMED; rebuild-from-base-URL is correct |

**The load-bearing decision does not hold in Spain.** Not because of A1 — the Twilio feature
probably works fine — but because Spanish law independently (a) prohibits the use of mobile
numbering for unsolicited commercial calls and (b) mandates carrier blocking of any Spanish CLI
arriving from abroad. Both have been in force since 2025-06-07. No amount of verification, and no
change to *which* number the SDR verifies, fixes (b). The compliant path is Twilio-provisioned
Spanish geographic or 800/900 numbers with a full NIF/DNI + local-address regulatory bundle per
tenant — i.e. exactly the cost and onboarding friction the architecture exists to avoid. The cost
model needs to be rebuilt, not patched.
