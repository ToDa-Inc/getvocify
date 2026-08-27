# Spain: caller ID law and what it does to BYO-CLI

**Status:** blocking finding, with a hard deadline of **2026-10-17**.
**Last revised:** 2026-08-27 (second pass — the first pass overstated two articles; corrections
marked below).

**Primary sources, both read directly:**
- [Orden TDF/149/2025, de 12 de febrero — consolidated, BOE-A-2025-2870](https://www.boe.es/eli/es/o/2025/02/12/tdf149/con)
- [Resolución SETID de 14 de abril de 2026 — BOE-A-2026-8409](https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8409)

Supporting analysis: [`legal-scope-analysis.md`](legal-scope-analysis.md) (article-by-article
scope), [`hubspot-calling-precedent.md`](hubspot-calling-precedent.md) (what the market leader
actually ships).

## The one-line version

Presenting the SDR's own number as caller ID is **not illegal for us** — Arts. 4 and 5 bind
operators, not callers — but it fails silently and partially, it is prohibited for our
*customer* when the number is a mobile, and from **2026-10-17** commercial calls in Spain may
only originate from the new **400** range, which can never be anyone's own number.

## Corrections to the first pass

Recorded deliberately. Two of these were overstatements that would have led to the wrong
remediation, and one was a hoped-for escape hatch that does not exist.

| First pass said | Correct position |
|---|---|
| Art. 4.4 obliges the terminating carrier to block our calls | **Too broad.** The duty fires only where the receiving operator holds that CLI as `asignado o portado` — *"un CLI que **el propio operador** tenga asignado o portado"*. A Movistar CLI reaching a Vodafone subscriber creates no Vodafone duty. It bites when caller and callee share an operator, or when that operator transits |
| Art. 5.1 blocks our traffic into Spain | **Narrower than stated.** Art. 2.2 names the obliged party as *"el operador que recibe la llamada por una interfaz internacional de interconexión"*. Domestic injection removes the trigger |
| "Flatly prohibited" | **Overstated.** Arts. 4 and 5 impose no duty on the caller at all. That is delivery risk, not illegality. Art. 9 is the one that binds our customer |
| B2B prospecting might be outside Art. 9 | **Does not hold.** The carve-out depended on Art. 66.1.b) Ley 11/2022 being consumer-scoped. Ley 11/2022 Anexo II ¶82–83 define `usuario` as `persona física o jurídica` — a company is an end user. Art. 9 has no consumer qualifier and `llamada comercial no solicitada` is undefined in the Order. Treat B2B as in scope |

Net effect of the corrections: the failure mode is **worse in practice and better in law** than
first stated. Worse, because a partial silent failure rate is harder to detect and harder to
debug than a clean block. Better, because we are not the sanctionable party under Arts. 4/5.

## What each provision actually does

### Art. 4.4 + 4.5 — partial, silent delivery failure

> **4.** Las llamadas recibidas por un operador, actuando este operador en terminación o
> tránsito, que presenten un CLI que el propio operador tenga asignado o portado deberán ser
> bloqueadas, salvo que se trate de un caso de itinerancia internacional [...]
>
> **5.** Este artículo se aplica independientemente de si la llamada se realiza dentro de
> España o entra en España desde el extranjero [...]

A self-range integrity check. If the SDR's number is Movistar's and the prospect is also on
Movistar, Movistar must block. If the prospect is on Vodafone, no duty arises there. Art. 4.5
means this holds domestically too, so it cannot be routed around.

Two things widen it: `asignado o portado` is disjunctive, so for a ported number both the
original block assignee and the current holder have a duty; and it covers **transit**, not just
termination, which matters because Telefónica carries heavy inter-operator transit.

The consequence is a **failure rate that clusters by terminating carrier**. We have deliberately
not estimated a percentage. What matters operationally is that a blocked call and a prospect
who did not pick up are indistinguishable in our telemetry — which is precisely why the design
can look like it works.

### Art. 5.1 — only over an international interconnect

> **1.** Deberán bloquearse las llamadas [...] recibidas desde el extranjero cuando presenten
> como CLI un número de teléfono español, salvo que se trate de un caso de itinerancia
> internacional.

Obliged party per Art. 2.2 is the operator receiving over an international interconnect
interface. A CPaaS delivering via a Spanish domestic interconnect does not trigger it. Art. 7.1,
the SMS twin, states the international-interface qualifier explicitly, which is good evidence
it is implicit here.

Art. 5.2 adds the operationally nastier alternative: where roaming cannot be determined the
operator **may suppress the CLI or flag it unverified** instead of blocking. The call connects
and the prospect sees "Número privado".

### Art. 9 — binds our customer, and B2B is in scope

> **1.** Se prohíbe la utilización de rangos de numeración atribuidos al servicio de
> comunicaciones móviles para la prestación de servicios de atención al cliente y para la
> realización de llamadas comerciales no solicitadas.
>
> **2.** El incumplimiento [...] será sancionado conforme a lo establecido en el artículo
> 107.19 de la Ley 11/2022.

Art. 2.3 scopes Chapter IV to *"quienes realizan llamadas comerciales no solicitadas"* — our
customer, not us. No consumer qualifier and no size threshold anywhere.

**Crucially, Art. 9 is not part of Ley 10/2025.** It sits in numbering law — Ley 11/2022 and
RD 2296/2004 — with its own scope clause. So Ley 10/2025's consumer-facing scope limits, which
do plausibly exempt a B2B SaaS from the 400 mandate, **do not reach Art. 9**. Being outside
Ley 10/2025 buys nothing here.

Two common arguments against applying Art. 9 to B2B prospecting, and why neither holds:

**"B2B doesn't count."** Ley 11/2022 Anexo II ¶82–83 define `usuario` as *"persona física o
jurídica"*, so a company is an end user. And the closest analogous regime is explicit: LSSI
Art. 21.1 prohibits unsolicited commercial communications to *"personas físicas como personas
jurídicas"* alike.

**"An SDR isn't selling, just booking a meeting."** The Spanish legal concept of *comercial* is
promotional purpose, not a completed transaction. LSSI Anexo f) defines *comunicación comercial*
as *"toda forma de comunicación dirigida a la promoción, **directa o indirecta**, de la imagen o
de los bienes o servicios de una empresa"*. Booking a demo is direct promotion of a service. No
money needs to change hands, and "indirecta" closes the gap even for a purely
relationship-building call.

Genuinely unsettled with no authority squarely on point, but asymmetric: the plain reading needs
no interpretive work, and the counter-argument requires reading in a limitation the text does
not contain. Assume it applies.

AEPD Circular 1/2023 Art. 5 gives B2B a rebuttable lawful-basis presumption via LOPDGDD
Art. 19 — but that is a data-protection safe harbour, not an exemption from a numbering rule.
A campaign can be perfectly clean under Art. 19 and still breach Art. 9 by dialling from a 6xx.

### Art. 10 — geographic numbering was permitted, until October

Art. 10.1 attributes 800/900 to these services *"además de"* their existing use — permissive,
not exclusive. Art. 10.3 exists only because 800/900 are not normally valid CLIs. The Order is
**silent on geographic numbering**, so 91x/93x was permitted. The "only 800/900" reading found
in some secondary commentary, including Telnyx's own Spain page, is not supported by the text.

That answer has now been overtaken by the 400 range.

## The 400 range — the deadline that changes everything

[Resolución SETID de 14 de abril de 2026](https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8409),
in force 2026-04-17, implementing Art. 16.3 of Ley 10/2025.

**Apartado sexto, second paragraph — unqualified:**

> Una vez cumplido dicho plazo, las llamadas comerciales **sólo podrán efectuarse a través del
> rango NXY = 400** no pudiendo utilizarse desde entonces ningún otro rango de numeración para
> la realización de llamadas comerciales.

The period is six months from entry into force: **2026-10-17**. The Ministry's press release
states operators will block commercial calls not originating from an assigned 400 number.

Three structural consequences, each from the text:

1. **A 400 number can never be the SDR's own number.** Apartado cuarto.1: only *"los operadores
   del servicio telefónico disponible al público"* may hold 400 numbers, assigned by the CNMC.
   "Present your own CLI" and "make a commercial call" become mutually exclusive in Spain.
2. **400 numbers cannot receive calls at all.** Apartado tercero.1: *"queda prohibido el
   establecimiento de llamadas que tengan como número de destino cualquier número perteneciente
   al rango NXY = 400"*. No callback, ever. This also rules out the 800/900 callback story we
   were considering as the conservative fallback.
3. **Destinations are limited** to end-user numbering — geographic, mobile, nomadic
   (tercero.4). Calls from 400 are treated as fixed-network originated for interconnect
   (tercero.3).

### Does the 400 mandate bind a B2B SaaS's customers? Probably not

Checked against the primary text, because it determines whether 2026-10-17 is our deadline.

**Ley 10/2025 Art. 2.1** covers providers of basic services of general interest — water, gas,
electricity, passenger transport, postal, electronic communications, financial services.

**Ley 10/2025 Art. 2.2** covers companies selling anything else *"destinados principalmente a
personas consumidoras y usuarias conforme al artículo 3 del Real Decreto Legislativo 1/2007"*
**and** meeting at least one threshold: 250+ employees, >€50M turnover, or >€43M balance sheet.

A B2B SaaS selling to businesses is outside both. Not a basic service of general interest, and
not selling to *personas consumidoras y usuarias* — Art. 3 TRLGDCU defines those as natural
persons, plus legal persons acting without a profit motive. A company buying software to sell
more software is neither.

**Conclusion:** the 400 exclusivity in apartado primero.2, which is expressly limited to *"las
empresas comprendidas en el ámbito de aplicación de la citada Ley"*, most likely does **not**
bind a B2B SaaS's customers. The 2026-10-17 deadline is probably not ours.

Three caveats that stop this being a clean pass:

1. **Apartado sexto is unqualified** and says commercial calls may only be made from 400 after
   the deadline, full stop. Primero.2 and Sexto contradict each other, unresolved.
2. **Ley 10/2025 Art. 16.4 mandates operator blocking** of calls that *"aparenten incumplir"*
   the identification duty — appearance-based and range-agnostic. An operator cannot know
   whether a given caller falls within Ley 10/2025's scope, so being legally out of scope does
   not guarantee delivery.
3. A customer of ours that *is* large and consumer-facing would be in scope. Our tenants are
   not uniform.

### The unresolved scope contradiction

**Apartado primero.2** limits the exclusivity to *"las empresas comprendidas en el ámbito de
aplicación de la citada Ley"* — Ley 10/2025, whose Art. 2.2 covers firms selling
*"destinados principalmente a personas consumidoras y usuarias"* above size thresholds
(250 staff / €50M turnover / €43M assets). A small B2B seller sits outside that.

**Apartado sexto** carries no such limitation.

Primero.2 and Sexto contradict each other and nobody has resolved it. The practical problem is
that the resolution is enforced by *operators*, and an operator cannot know whether a given
customer falls inside Ley 10/2025's scope — so whatever blocking they implement will be based
on observable behaviour, not legal scope. Ley 10/2025 Art. 16.4 reportedly permits
behaviour-based blocking on `indicios` of commercial calling, range-agnostic. Under that,
switching to a landline does not help.

**Open, and it needs a lawyer:** does a B2B SaaS whose customers sell to businesses fall within
Ley 10/2025? If not, Primero.2 does not bind them — but Sexto arguably does, and operator
blocking may not distinguish either way.

## The decisive external evidence

HubSpot ships **exactly** the feature we built. "Register an outbound phone number", verified by
SMS or voice code:

> Registering an outbound phone number allows you to make calls from the HubSpot CRM while
> displaying your existing mobile or office number as the Caller ID.

HubSpot Calling is explicitly *"powered by Twilio"*. So this is the same design, on the same
carrier, shipped by the market leader at scale.

And HubSpot's own supported-countries page documents that it does not work in Spain:

> [...] or placing calls that present a Spanish Caller ID (all HubSpot registered numbers), you
> may receive an error message, and the call will not be completed.

HubSpot cites Orden TDF/149/2025 by name and deep-links the BOE. Spain appears in HubSpot's
provided-number and porting lists as **"Spain (local)" only — geographic, never mobile**. The
same page documents CLI suppression or blocking in Austria, Belgium, Finland, Norway,
Switzerland, Japan and South Africa.

This settles the empirical question. The market leader tried BYO-CLI, hit the same wall, and
its answer in Spain is carrier-owned geographic numbering — provisioned or ported.

### Field observation

One data point from our own testing, recorded with its caveats because it is the only
real-world evidence we have.

A registered **personal `+34 6xx` mobile** was used as caller ID in HubSpot in **June 2026** and
calls completed normally. That date is a year after Arts. 5.1 and 9 took effect and two months
after the 400 resolution, so it is not a pre-enforcement artefact.

**What this establishes:** the Art. 4.4 / 5.1 **blocking** obligations are not being enforced
reliably by Spanish operators, at least on the routes tested. This contradicts HubSpot's own
country-support page, which says such calls "will not be completed." Weight it accordingly —
it is first-hand and recent, and our earlier assumption that delivery would fail was too
pessimistic.

**What it does not establish:** anything at all about Art. 9. The two regimes are enforced by
different mechanisms, and conflating them is the central error to avoid here:

| | Enforcement mechanism | Does a completed call tell you anything? |
|---|---|---|
| Arts. 4 / 5 | Technical blocking by the operator | Yes — completion means blocking did not fire |
| Art. 9 | Administrative sanction by the CNMC against the caller | **No.** Art. 9 never blocked anything. Completion is not evidence of compliance and cannot be |

**Sanction size under Art. 9.2 → Art. 107.19 (infracción grave) → Ley 11/2022 Art. 109:**
fine up to **€2,000,000** (109.1.c); an order barring use of the offending number for up to
**two years** (109.4), which is severe when the number is someone's personal mobile; and up to
**€30,000** personally on legal representatives or directors (109.5). Sanctionable party is
*"quienes realizan llamadas comerciales no solicitadas"* (Art. 2.3) — our customer, not us.

**The useful consequence.** If blocking is not being enforced, the constraint that ruled out
geographic numbering disappears, and a `+34 9x` landline CLI becomes the best available option:
clean under Art. 9 (not a mobile range, and the Order is silent on geographic numbering) *and*
empirically delivering. Same implementation cost as the mobile, without the exposure. That is a
better answer than the provisioned-DID-only conclusion reached earlier in this document.

## Honest risk assessment

| Configuration | Legal position | Practical delivery | Verdict |
|---|---|---|---|
| Own **mobile**, B2C | Art. 9 breach by our customer | Partial silent failure | Prohibited |
| Own **mobile**, B2B | Art. 9 breach on the plain reading; unsettled | Partial silent failure | Legally exposed, practically under-enforced. Do not default to it |
| Own **geographic landline** | Clean on Art. 9. Silent on geographic numbering | Still hits Art. 4.4 on same-operator combinations | Viable until 2026-10-17 |
| Carrier-provisioned `+34 9x` | Clean. What HubSpot does | Works | Viable now; 400 question from October |
| 400 range | The only explicitly sanctioned path from October | Works, **no callback possible** | Requires a carrier holding 400 assignments |

Note the trap in row 3: moving SDRs from mobile to landline fixes Art. 9 and does **nothing**
for Art. 4. Anyone proposing "just use a landline" is solving the wrong half of the problem.

## Enforcement reality

No published Art. 4.6 / 5.3 exceptions were found. No Art. 5.2 criteria resolution. No CNMC
sanction under Art. 9 located. These are negative search results, not proof of absence.

The most informative real-world signal is AEERC/CEX industry lobbying arguing that Art. 5.1
would break offshore and nearshore contact centres — structurally the same fact pattern as
ours. Voice blocking was never postponed; only the SMS alias regime slipped, to 2026-09-15.

## Scope limit and disclaimer

This covers **Spain**. BYO-CLI may remain viable elsewhere, but HubSpot's country page shows
at least seven other jurisdictions with CLI restrictions, so do not assume Spain is an outlier.
Run the same primary-source check per market.

This is an engineering reading of primary sources done to unblock an architecture decision, not
legal advice. Three questions need a qualified Spanish telecoms lawyer: whether B2B prospecting
falls under Art. 9; whether a B2B SaaS's customers fall within Ley 10/2025's scope; and how the
Primero.2 / Sexto contradiction resolves.
