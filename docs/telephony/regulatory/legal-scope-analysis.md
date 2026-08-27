# Spain — CLI / caller-ID legal scope for B2B outbound SDR calling

**Scope of this note:** a B2B SaaS product where an SDR places outbound calls from a browser, presenting the SDR's own existing Spanish phone number as CLI, with traffic originating on a CPaaS (Twilio) and terminating in Spain.

**Date of research:** 27 August 2026. Law stated as at that date, using the *consolidated* BOE texts.

**Headline correction before anything else:** the question set is framed around Orden TDF/149/2025. That Order is no longer the whole picture. Two later instruments materially change the answer and were not in the brief:

- **Ley 10/2025, de 26 de diciembre, por la que se regulan los servicios de atención a la clientela** — <https://www.boe.es/eli/es/l/2025/12/26/10>
- **Resolución de 14 de abril de 2026, de la SETID, por la que se atribuyen recursos públicos de numeración para la prestación del servicio de llamadas comerciales** (creates the **NXY = 400** range) — <https://www.boe.es/buscar/act.php?id=BOE-A-2026-8409> (BOE-A-2026-8409, BOE núm. 93 of 16/04/2026)

See Q4 and Q6. The 400-range regime bites from **~17 October 2026**, i.e. roughly seven weeks from the date of this note.

---

## Verdict summary

| # | Your reading | Verdict |
|---|---|---|
| 1 | Art. 4.4 blocking duty arises only where the CLI is in the receiving operator's own assigned/ported numbering | **CONFIRMED**, with two material corrections that widen it (portability double-hook; transit) and one drafting tension (Art. 2.2 "podrán" vs Art. 4.4 "deberán") |
| 2 | Art. 5.1 applies only to traffic entering over an international interconnect interface; domestic Spanish injection escapes it | **CONFIRMED on the obliged-party analysis, AMBIGUOUS on anti-circumvention.** The trigger is interface-anchored, not provenance-anchored. But Art. 5.4 and RD 381/2015 give a regulator a route to attack deliberate re-labelling |
| 3a | Art. 9 prohibits mobile numbering as CLI for unsolicited commercial calls | **CONFIRMED** |
| 3b | "Llamadas comerciales no solicitadas" may be consumer-scoped, so B2B prospecting escapes Art. 9 | **CORRECTED → the term is undefined and the point is GENUINELY UNSETTLED, but the better textual reading is that B2B is IN scope.** Do not rely on a B2B carve-out from Art. 9 |
| 4 | Geographic 91x/93x is permitted because the Order only bans mobile | **CORRECTED.** True of the Order in isolation (it is silent), but **superseded**: from ~17 Oct 2026 the SETID Resolution of 14 April 2026 makes NXY=400 the exclusive origin range for commercial calls |
| 5 | — | Blocking obligations are live and partially implemented; **no published Art. 4.6 / 5.3 exception register located**; no located CNMC sanction under Art. 9 |
| 6 | "Flatly prohibited" | **OVERSTATED as to Arts. 4 and 5; UNDERSTATED as to what is coming in October 2026** |

---

## Q1 — Article 4.4 scope

### The text

Orden TDF/149/2025, Art. 4.4 (<https://www.boe.es/eli/es/o/2025/02/12/tdf149/con>):

> «4. Las llamadas recibidas por un operador, actuando este operador en terminación o tránsito, que presenten un CLI que el propio operador tenga asignado o portado deberán ser bloqueadas, salvo que se trate de un caso de itinerancia internacional, en cuyo caso se aplicará lo establecido en el artículo 5.2.»

And Art. 4.5:

> «5. Este artículo se aplica independientemente de si la llamada se realiza dentro de España o entra en España desde el extranjero a través de una interfaz internacional de interconexión.»

### Verdict: CONFIRMED

Your revised reading is correct on its face. The operative limitation is **«que el propio operador tenga asignado o portado»** — the possessive is doing real work. The rule is a *self-range integrity check*: an operator receiving an inbound call from another network that bears a CLI drawn from that operator's own numbering holdings is, by construction, looking at something that should be impossible (a call from its own subscriber would have originated on its own network), and must therefore drop it. Roaming is the carved-out explanation for why the impossible thing can legitimately happen, hence the Art. 5.2 cross-reference.

If the SDR's number is a Movistar number and the prospect is a Vodafone subscriber, **Vodafone has no Art. 4.4 duty**, because the CLI is not in Vodafone's assigned or ported holdings.

Note also what Art. 4 does *not* catch. A real, live, subscriber-allocated Spanish number presented as CLI does not trigger:

- **Art. 4.1** — the number is attributed and format-coherent;
- **Art. 4.2** — «numeraciones que no hayan sido asignadas por la Comisión Nacional de los Mercados y la Competencia a ningún operador» — it has been assigned;
- **Art. 4.3** — «numeraciones que le hayan sido asignadas, subasignadas o portadas y que ese operador todavía no haya adjudicado a ningún cliente» — it *has* been allocated to a customer.

So Art. 4.4 is the only limb of Art. 4 in play. That alone means "flatly prohibited by Art. 4" was wrong.

### Correction 1 — portability creates a double hook, not a single one

"Asignado **o** portado" is disjunctive and covers two different relationships to a number:

- **asignado** — the numbering *block* was assigned to that operator by the CNMC;
- **portado** — the individual number has been ported *in* to that operator.

For a number that has been ported, these sit with **different operators**. The original block assignee retains the CNMC block assignment; the recipient operator holds it as ported-in. On the natural reading, **both** operators have an Art. 4.4 duty in respect of that CLI. Spanish mobile portability volumes are high, so a large share of real SDR numbers will have two operators, not one, holding a blocking duty.

This is a genuine widening relative to your framing.

### Correction 2 — "same operator" is not the right practical test; transit matters

Art. 4.4 covers the operator «actuando este operador en **terminación o tránsito**». Your consequence statement ("the rule bites only when caller and callee are on the same operator") captures the termination leg but omits transit. The correct test is:

> Art. 4.4 bites if **any** operator in the delivery path — terminating **or transiting** — holds the CLI as assigned or ported.

This matters disproportionately in Spain, where the incumbent carries a large volume of inter-operator transit. If the SDR's number sits in a Telefónica-assigned range, the chance that Telefónica appears somewhere in the path as transit provider — even when the prospect is on a different retail brand — is materially higher than its retail share alone would suggest.

### Quantifying the practical consequence

Honest answer: **it cannot be quantified precisely from public sources, and any single percentage would be false precision.** What can be said with confidence:

- The failure mode is **partial and non-deterministic**, not a uniform block. Some calls complete, some are silently dropped, and which ones depends on the CLI's home operator, its portability history, and the wholesale route chosen for that particular call.
- The exposure per call is approximately: `P(terminating operator holds the CLI) + P(a transit operator in the path holds the CLI)`.
- Spanish mobile retail is concentrated across roughly four groups (MasOrange, Movistar/Telefónica, Vodafone, Digi), so the termination term alone is a double-digit percentage for a randomly chosen SDR/prospect pair, and higher if the SDR base clusters on one operator — which it will, since sales teams tend to buy corporate lines in bulk from one carrier.
- **This is exactly the profile that produces the stakeholder's "it demonstrably works in production" observation.** A feature that fails 15–30% of the time, silently, with no error surfaced to the rep, looks like it works. It does not look like a compliance failure; it looks like the prospect didn't pick up. That is the single most important thing to tell the stakeholder.

### Flagged drafting tension — Art. 2.2 vs Art. 4.4

Art. 2.2 states:

> «2. En el caso del artículo 4 resultará obligado al bloqueo el operador que origina la llamada. En el caso del artículo 5, resultará obligado al bloqueo el operador que recibe la llamada por una interfaz internacional de interconexión. **El resto de operadores que transiten o terminen la llamada podrán realizar el bloqueo** en los supuestos recogidos en dichos artículos.»

Art. 2.2 says non-originating operators **may** («podrán») block under Art. 4. Art. 4.4 says calls received in termination or transit **must** («deberán») be blocked. These are in direct tension.

The better resolution is that Art. 4.4 is *lex specialis*: it is the one paragraph of Art. 4 addressed expressly to operators «actuando en terminación o tránsito», so its mandatory "deberán" governs that scenario, and Art. 2.2's permissive "podrán" covers non-originating operators for paragraphs 4.1–4.3. That is the reading that gives both provisions work to do.

**But this is a real ambiguity, and it cuts in your favour if resolved the other way.** If Art. 2.2 is read as controlling, then for a call originated abroad (where there is no Spanish "operador que origina la llamada"), Art. 4 imposes no mandatory duty on anyone, and terminating operators merely have a discretion. Operators exercising a discretion behave less uniformly than operators under a duty — which is again consistent with observed partial delivery. I have found no CNMC or SETID guidance resolving this.

---

## Q2 — Article 5.1 scope

### The texts

Art. 5.1:

> «1. Deberán bloquearse las llamadas de servicios de comunicación vocal, recibidas desde el extranjero cuando presenten como CLI un número de teléfono español, salvo que se trate de un caso de itinerancia internacional.»

Article heading: «Artículo 5. Bloqueo de llamadas con **origen internacional** identificadas por un CLI del plan nacional de numeración fija o móvil.»

Art. 2.2, obliged party: «En el caso del artículo 5, resultará obligado al bloqueo **el operador que recibe la llamada por una interfaz internacional de interconexión**.»

Art. 3.e), definition:

> «e) Interfaz internacional de interconexión: punto en el que una llamada internacional llega a España por una interfaz que pertenece a un proveedor de servicios de comunicaciones electrónicas inscrito en el Registro de Operadores gestionado por la Comisión Nacional de los Mercados y la Competencia.»

Art. 5.4:

> «4. Las llamadas telefónicas internacionales sólo podrán recibirse por el operador obligado en circuitos dedicados y claramente diferenciados de las llamadas telefónicas nacionales. La distinción deseada puede lograrse utilizando circuitos físicos separados o, virtualmente, distinguiendo las llamadas mediante señalización.»

Preamble:

> «el artículo 5 [...] obliga a los operadores a bloquear las llamadas con origen internacional identificadas por un CLI del plan nacional de numeración, salvo que se trate de un caso de itinerancia internacional.»

### Verdict: CONFIRMED on the obliged-party analysis; AMBIGUOUS on anti-circumvention

**What «recibidas desde el extranjero» is doing legally.** Read alone, it is a factual criterion about provenance. But it does not stand alone. Art. 5.1 is a passive construction with no named duty-holder — «Deberán bloquearse» — and the duty-holder is supplied exclusively by Art. 2.2, which anchors it to **the operator receiving the call over an international interconnect interface**, a term with a hard definition in Art. 3.e).

The consequence is structural: **if no operator receives the call over an international interconnect interface, Art. 5 has no obliged party and therefore no operative duty.** The phrase «recibidas desde el extranjero» describes the *class of call* the duty-holder must screen; it is not itself a free-standing prohibition addressed to the world.

Two further textual supports:

1. **Art. 5.4 confirms the classification is by circuit/signalling, not by true provenance.** It requires international calls to arrive on dedicated, clearly differentiated circuits — physically or by signalling. The regime's operational premise is that "international" is a property of *how the traffic is presented at interconnect*, because that is the only thing an operator can actually observe at the point of screening.
2. **The drafters coupled the two concepts explicitly elsewhere.** Art. 4.5 says «entra en España desde el extranjero **a través de una interfaz internacional de interconexión**», and Art. 7.1 (the SMS analogue of Art. 5.1) says «recibido desde el extranjero **a través de una interfaz internacional de interconexión**». Art. 5.1 omits the qualifier. Two readings are available: either the omission is deliberate and Art. 5.1 is broader, or — more plausibly given Art. 2.2 supplies it anyway — it is drafting economy. The Art. 7.1 comparison is the strongest single argument that the qualifier was understood to be implicit.

**So: if a CPaaS terminates Spanish traffic as a Spanish-licensed operator inscribed in the CNMC Registro de Operadores, or via a Spanish wholesale partner over domestic interconnect, the Art. 5.1 trigger is not met at that handoff.** That is the correct legal analysis and it is the mechanism by which products like the one described actually deliver traffic in Spain.

### Where this is genuinely ambiguous

Three counter-arguments, none of which I can resolve on published sources:

1. **Circumvention.** Routing traffic that is in substance foreign-originated over a domestic interconnect specifically to avoid the international classification is precisely the mischief Chapter II targets. A regulator could characterise it as `tráfico irregular con fines fraudulentos` under **Real Decreto 381/2015, de 14 de mayo**, Art. 2.2.a), which is the enabling provision the Order itself develops (see the preamble: «el artículo 4 desarrolla lo establecido en el artículo 2.2.a) del Real Decreto 381/2015»).
2. **Art. 5.4 as an affirmative segregation duty.** If an operator *knows* traffic is international, Art. 5.4 arguably obliges it to receive that traffic on differentiated circuits — i.e. it cannot lawfully accept known-international traffic on a national interconnect and thereby launder its classification. This reading has force but I found no authority applying it.
3. **Art. 4 survives regardless.** Even on the most favourable Art. 5 analysis, Art. 4.5 expressly applies Art. 4 «independientemente de si la llamada se realiza dentro de España o entra en España desde el extranjero». Domestic injection does not escape Art. 4.4. So the Q1 exposure persists in full.

**Net:** domestic injection removes the Art. 5.1 systematic-block problem. It does not remove the Art. 4.4 partial-block problem, and it carries an unquantified regulatory-characterisation risk.

---

## Q3 — Article 9 scope (the crux)

### The text

> **«Artículo 9. Prohibición de utilización de la numeración móvil para llamadas de atención al cliente o para la realización de llamadas comerciales no solicitadas.**
>
> 1. Se prohíbe la utilización de rangos de numeración atribuidos al servicio de comunicaciones móviles para la prestación de servicios de atención al cliente y para la realización de llamadas comerciales no solicitadas.
>
> 2. El incumplimiento de la prohibición establecida en el apartado 1 será sancionado conforme a lo establecido en el artículo 107.19 de la Ley 11/2022, de 28 de junio, General de Telecomunicaciones.»

In force since **7 June 2025** (Disposición final tercera.4: «El artículo 9 de la presente orden producirá efectos a los tres meses de su entrada en vigor», entry into force being 7 March 2025).

### Q3(a) — CLI, or "service number" more broadly? Verdict: CONFIRMED (it reaches CLI)

It reaches both, and CLI is the operative limb for outbound prospecting.

Art. 9 covers two distinct activities. For «prestación de servicios de atención al cliente», the prohibited use is the mobile number as the *published inbound service number*. For «realización de llamadas comerciales no solicitadas», the activity is outbound call *making*, and the only sense in which mobile numbering is "utilizada" in making an outbound call is as the originating line and the presented CLI. There is no third possibility.

The preamble confirms the identification purpose:

> «En primer lugar, **para permitir una mejor identificación de estas llamadas**, en desarrollo del artículo 27.7 del Reglamento sobre mercados de comunicaciones electrónicas, acceso a las redes y numeración, aprobado por Real Decreto 2296/2004, de 10 de diciembre, se prohíbe usar **para estas llamadas** numeración móvil, lo que obliga, asimismo, a revisar la redacción de la Resolución de 27 de mayo de 2013, por la que se modifica la atribución de los rangos de numeración para comunicaciones móviles.»

«Para estas llamadas» — for these calls. That is call-origination language, and identification is only meaningful at the CLI.

**Reading with Art. 10 reinforces this.** Art. 10.3:

> «3. Se autoriza, con carácter general, la utilización de numeración 800 y 900 **en el campo del CLI**, de acuerdo al artículo 61.2 y 71 del Reglamento sobre las condiciones para la prestación de servicios de comunicaciones electrónicas [...] aprobado por Real Decreto 424/2005, de 15 de abril, con objeto de que el usuario llamado pueda devolver las llamadas a estos números de forma gratuita.»

Art. 10.3 is an *enabling* provision. 800/900 are ordinarily inbound-only and are not normally valid CLIs, so an express authorisation was needed to allow them in the CLI field. RD 424/2005 Art. 61.2, the cited hook, is the provision governing «visualización y limitación de la identificación de la línea de origen»:

> «2. Las disposiciones sobre visualización y limitación de la identificación de la línea de origen y de la línea conectada y sobre el desvío automático de llamadas se aplicarán, en los términos establecidos en la sección 3.ª de este capítulo, a las líneas de abonados conectadas a centrales digitales y, cuando sea técnicamente posible y no exija una inversión desproporcionada por el operador, a las líneas de abonados conectadas a centrales analógicas. [...]» (<https://www.boe.es/eli/es/rd/2005/04/15/424/con>)

So Chapter IV is legislating explicitly in the CLI layer. Art. 9 prohibits one class of CLI; Art. 10 authorises another. **The mobile-number-as-CLI reading is the correct one, and it is the reading the whole chapter is built around.**

Note also **Disposición final segunda**, which rewrites the permitted-uses list for mobile ranges in the Resolución of 27 May 2013:

> «b) La provisión de servicios asociados a redes públicas de comunicaciones móviles como son, entre otros, la prestación de servicios de red privada virtual soportados sobre redes de comunicaciones móviles, o su empleo en facilidades del tipo multilínea o multidispositivo.»

The preamble says the Art. 9 prohibition «obliga, asimismo, a revisar la redacción» of that Resolution — i.e. the pre-existing attribution had to be narrowed to make room for the ban. *(I have not verified the pre-amendment wording of Primero.1.b) and have not asserted what it said.)*

### Q3(b) — Does "llamadas comerciales no solicitadas" cover B2B prospecting?

**Verdict: CORRECTED. Your hoped-for B2B carve-out is not available on the text of the Order. The point is genuinely unsettled, but the better reading is that B2B is IN scope. Do not build on the carve-out.**

This is the answer you asked me not to make comfortable, so here it is plainly.

**1. The Order does not define the term.** Art. 3 («Definiciones») defines seven terms — *alias*, *número de teléfono español*, *identificador de línea llamante o CLI*, *número de teléfono llamado*, *interfaz internacional de interconexión*, *itinerancia internacional*, *servicio de comunicaciones vocales*. **«Llamada comercial no solicitada» is not among them.** Nor is it defined anywhere else in the Order. This is a real gap and it is the source of the whole ambiguity.

**2. Art. 9 itself contains no consumer limitation.** It says «llamadas comerciales no solicitadas», full stop. A cold call from an SDR to a business contact who did not ask for it is, on ordinary Spanish usage, a *llamada comercial no solicitada*. There is nothing in the words to exclude it.

**3. The obliged-party provision is drafted around the caller, not the callee.** Art. 2.3:

> «3. Las obligaciones establecidas en el capítulo IV de la presente orden aplican a los prestadores de servicios de atención al cliente o a quienes realizan llamadas comerciales no solicitadas.»

Again: no consumer qualifier. The trigger is *who is calling and why*, not *who is being called*.

**4. The Art. 66.1.b) reference in the preamble does not import a consumer limitation — and would not help you even if it did.** The Chapter IV preamble says:

> «se adoptan medidas para garantizar la correcta identificación de la numeración utilizada [...] que **en todo caso deberán garantizar los derechos de los usuarios conforme a lo establecido en el artículo 66.1.b) de la Ley 11/2022**»

This is a "without prejudice" clause — a floor, not a ceiling. It says Chapter IV must not undercut Art. 66.1.b) rights; it does not say Chapter IV's scope is co-extensive with them.

And critically, **Art. 66.1.b) is not consumer-scoped either.** Its beneficiaries are «los usuarios finales de los servicios de comunicaciones interpersonales disponibles al público basados en la numeración». Ley 11/2022 Anexo II defines those terms:

> «82. Usuario: **una persona física o jurídica** que utiliza o solicita un servicio de comunicaciones electrónicas disponible para el público.»
>
> «83. Usuario final: el usuario que no suministra redes públicas de comunicaciones electrónicas o servicios de comunicaciones electrónicas disponibles para el público, ni tampoco los comercializa.»

(<https://www.boe.es/buscar/act.php?id=BOE-A-2022-10757>)

**A company is a *persona jurídica*, is therefore a *usuario*, and is therefore a *usuario final*.** The premise that Art. 66.1.b) is a consumer-only provision — which was doing the work in your B2B theory — **is wrong at the level of the LGTel's own definitions.** Calling a company switchboard is calling an *usuario final*.

**5. The AEPD's Circular 1/2023 does not create a B2B exemption from the calling prohibition.** Circular 1/2023, de 26 de junio (<https://www.boe.es/eli/es/cir/2023/06/26/1>) is the AEPD's criteria document on Art. 66.1.b). Two things must be separated.

*What it does say about B2B* — Art. 5:

> «Artículo 5. Tratamiento de datos de contacto, de empresarios individuales y de profesionales liberales.
>
> Se presumirá lícito el tratamiento de los datos de las personas físicas que presten servicios en una persona jurídica, empresarios individuales y profesionales liberales, en los casos y términos previstos en el artículo 19 de Ley Orgánica 3/2018, de 5 de diciembre.»

And in the preamble:

> «Tratándose de números correspondientes a personas físicas que presten servicios en personas jurídicas o de empresarios individuales y de profesionales liberales [...] operará la presunción contenida en el artículo 19 de la Ley Orgánica 3/2018 [...] en cuanto se refiera a la oferta de productos y servicios relacionados con la actividad profesional o empresarial y no se trate de entablar relación en cuanto tales personas físicas.»

*What that actually is:* a **rebuttable presumption of a lawful basis under Art. 6.1.f) GDPR** for processing B2B contact data (LOPDGDD Art. 19). It is a *data-protection* safe harbour. It answers "may I lawfully hold and use this person's work number to call them about their business?" — and the answer is generally yes.

*What it is not:* an exemption from a *numbering* rule. Art. 9 of the Order is not a data-protection provision, is not enforced by the AEPD, and does not turn on whether you have a lawful basis. It is a condition attached to the use of a public numbering resource, enforced through the LGTel numbering regime. **You can have a perfect LOPDGDD Art. 19 legitimate-interest position for the call and still breach Art. 9 by making it from a 6xx number.** These are two independent regimes and conflating them is the single most common error in the secondary commentary on this point.

Note also the Circular's own framing of its reach, which is broad as to callers, not narrow as to callees:

> «el cual resulta de aplicación a todos los responsables del tratamiento que realicen llamadas comerciales, con independencia del sector al que pertenezcan, al tratarse de una normativa referida a los derechos de los consumidores y usuarios que se aplica de manera general a cualquier empresa o empresario que utilice aquellos servicios y no solamente a las compañías operadoras en el sector.»

The phrase «derechos de los consumidores y usuarios» is the only consumer-flavoured hook in the whole chain, and it appears in a *recital of an AEPD circular about a different statute*, describing why the rule binds all sectors of caller. It is thin material on which to build a B2B exemption from a ministerial numbering prohibition.

**6. LSSI Art. 21 is not in point.** Ley 34/2002 (LSSI) Art. 21 governs unsolicited commercial communications «por correo electrónico u otro medio de comunicación electrónica equivalente» — email and SMS, not voice calls. Circular 1/2023 borrows Art. 21.2's *criteria* by analogy («al existir identidad de razón») for the legitimate-interest balancing, but LSSI Art. 21 does not itself regulate voice.

**7. LOPDGDD Art. 23 (sistemas de exclusión publicitaria) is a live parallel obligation, not a scope limiter.** Circular 1/2023 Art. 4: «Deberán consultarse previamente los sistemas de exclusión publicitaria, en los casos y términos previstos en el artículo 23 de la Ley Orgánica 3/2018». This is the Lista Robinson duty. It sits alongside Art. 9 and does not narrow it.

### The honest characterisation

**Arguments that B2B is in scope (stronger):** the term is undefined and therefore takes its ordinary meaning; Arts. 9 and 2.3 contain no consumer qualifier; Art. 66.1.b) — the referenced right — expressly protects *personas jurídicas*; the mischief (unidentifiable 6xx calls) is identical whoever picks up.

**Arguments that B2B is out of scope (weaker but not frivolous):** the Order's preamble is written almost entirely in the register of «consumidores»; Art. 10's rationale is «de modo que, devolver las llamadas a estos números, resulte gratuito para **los consumidores**»; Chapter IV is headed by a consumer-protection purpose; the Consejo de Consumidores y Usuarios was a mandatory consultee. A purposive reading could confine Chapter IV to B2C. **I have found no CNMC resolution, SETID resolution, court decision, or official guidance adopting that reading**, and I would not expect a regulator to volunteer it.

**Conclusion: genuinely unsettled, but asymmetric.** The textual reading (B2B in scope) is available to a regulator immediately and requires no interpretive work. The purposive reading (B2B out) requires an authority to read a limitation into a provision that does not contain one. **Treat Art. 9 as binding on B2B prospecting.**

There is also a practical trap even if the carve-out were good: an SDR cannot reliably tell in advance whether a given contact is a *persona jurídica* employee, an *empresario individual*, or a *profesional liberal* whose line is simultaneously personal. A theory of compliance that depends on correctly classifying the callee before dialling is not operable at SDR volumes.

### Q3(c) — Sanctionable party and penalty range

**Sanctionable party.** Art. 2.3 is explicit: Chapter IV binds «los prestadores de servicios de atención al cliente o **a quienes realizan llamadas comerciales no solicitadas**». That is **the calling business — the SaaS customer whose SDRs are dialling — not the operator and not the CPaaS.** Operators are the obliged parties for Chapters II and III (Art. 2.1), not Chapter IV.

For the product, the practical allocation is:
- **Primary exposure: the customer** (the employer of the SDRs), as the entity that «realiza» the calls.
- **Secondary/contested: the SaaS vendor.** Whether a platform that provisions, configures and executes the dialling «realiza» the calls is untested. There is no authority on this. A vendor that ships a default configuration presenting mobile CLIs, and markets it as a feature, is not obviously outside the phrase.

**Penalty.** Art. 9.2 routes to **Ley 11/2022 Art. 107.19**, which sits in «Artículo 107. Infracciones graves»:

> «19. El incumplimiento de las condiciones establecidas en los planes nacionales de numeración o sus disposiciones de desarrollo o en las atribuciones y asignaciones de los derechos de uso de los recursos de numeración incluidos en los planes de numeración.»

Sanctions, Art. 109.1.c):

> «c) por la comisión de infracciones graves se impondrá al infractor multa por importe de hasta dos millones de euros.
>
> Por la comisión de infracciones graves tipificadas en las que la Comisión Nacional de los Mercados y la Competencia tenga competencias sancionadoras se impondrá al infractor multa por importe de hasta el duplo del beneficio bruto obtenido como consecuencia de los actos u omisiones que constituyan aquellas o, en caso de que no resulte aplicable este criterio, el límite máximo de la sanción será el uno por ciento del volumen de negocios total obtenido por la entidad infractora en el último ejercicio;»

Two accessory sanctions matter commercially and are usually omitted from the secondary commentary:

> «4. Las sanciones impuestas por vulneración de las condiciones establecidas para la utilización de la numeración podrán llevar aparejada **orden de imposibilidad de uso del número o números** a través de los cuales se ha producido el incumplimiento, por un período máximo de dos años.» (Art. 109.4)

> «5. Además de la sanción que corresponda imponer a los infractores, cuando se trate de una persona jurídica, se podrá imponer una multa de hasta [...] 30.000 euros en el caso de las infracciones graves [...] **a sus representantes legales o a las personas que integran los órganos directivos**[...]» (Art. 109.5)

Art. 109.4 is the one to flag to a stakeholder: the remedy is not only a fine but potential **loss of use of the SDR's own number for up to two years**. For a rep whose number is their professional identity, that is a severe and very concrete outcome.

Note the ceiling is «hasta» — up to. Two million euros is the statutory maximum for the category, not an expected figure for a first-instance numbering breach by a mid-sized firm. Presenting €2M as the likely exposure would be as misleading as presenting zero.

---

## Q4 — Is geographic (landline) numbering permitted as CLI?

### Verdict: CORRECTED — the Order is SILENT, but silence is no longer the answer

**As to Orden TDF/149/2025 in isolation: yes, the Order is silent on geographic numbering, and geographic CLI was permitted.**

- Art. 9 prohibits **only** «rangos de numeración atribuidos al servicio de comunicaciones móviles». Geographic ranges are not mobile ranges.
- Art. 10.1 is **permissive, not exclusive**: «Se atribuye los segmentos N=8 y 9 [...] **además de** a los servicios de cobro revertido automático, a los servicios de atención a clientes y a la realización de llamadas comerciales no solicitadas.» «Además de» adds a use to the 800/900 attribution; it does not make 800/900 the sole lawful origin.
- Art. 10.3's authorisation of 800/900 «en el campo del CLI» was necessary *because* those ranges are otherwise not valid CLIs. Geographic numbers have always been valid CLIs and needed no such authorisation. **Art. 10.3's existence is evidence that geographic numbering was assumed lawful, not evidence that it was displaced.**

**The split in secondary commentary is real and is mostly sloppiness.** One camp reads Art. 10 as exclusive and says only 800/900 may be used (e.g. Baker Tilly: «deberán utilizar numeración permitida a tal efecto, como los números 800, 900 o numeración corta autorizada» — <https://www.bakertilly.es/publicaciones/nueva-normativa-para-comunicaciones-empresariales-y-fraude-telefonico>; Inmonews goes further: «Emplear exclusivamente numeración 800 o 900» — <https://www.inmonews.es/orden-tdf-149-2025-llamadas-comerciales-no-solicitadas-consecuencias-inmobiliarias/>). The other camp correctly reads geographic as still available (Legitec: «Numeraciones fijas geográficas. Números 800 o 900» — <https://legitec.com/nueva-prohibicion-de-llamadas-comerciales-desde-moviles-lo-que-debes-saber-sobre-la-orden-tdf-149-2025/>; Enreach: «se habilita para este fin la numeración 800/900 y **es posible utilizar numeración geográfica**» — <https://enreach.es/blog/como-afecta-la-orden-tdf1492025-a-las-llamadas-y-sms-de-tu-empresa/>). **The second camp was right on the Order.**

### But this is now superseded — the 400 range

**Resolución de 14 de abril de 2026, de la SETID** (BOE-A-2026-8409, in force 17 April 2026) attributes the **NXY = 400** range to commercial calls and makes it exclusive.

Preamble:

> «La utilización de recursos de numeración no específicamente atribuidos a llamadas comerciales como número de origen de dichas comunicaciones dificulta la identificación por parte del usuario final de la naturaleza de la llamada recibida y complica las labores de supervisión del uso de los recursos públicos de numeración.»

Apartado Primero:

> «1. Se atribuye el código 400, coincidente con las tres primeras cifras del número nacional (cifras NXY) del Plan Nacional de Numeración Telefónica, para la realización de llamadas comerciales [...]
>
> 2. Conforme a lo establecido en el artículo 16.3 Ley 10/2025, de 26 de diciembre, por la que se regulan los servicios de atención a la clientela, **las empresas comprendidas en el ámbito de aplicación de la citada Ley** no podrán utilizar ningún otro rango de numeración distinto del rango NXY = 400 para la realización de llamadas comerciales, salvo en los casos exceptuados por la disposición transitoria única, apartado 4 de dicha Ley.»

Apartado Segundo.1:

> «1. Los números comprendidos en el rango NXY = 400 se destinarán **exclusivamente como origen de llamadas comerciales salientes, sin habilitación para la recepción de llamadas entrantes**.»

Apartado Tercero.1:

> «1. Los operadores del servicio telefónico disponible al público estarán obligados a abrir en sus redes el rango de numeración atribuido en la presente resolución. No obstante, queda prohibido el establecimiento de llamadas que tengan como número de destino cualquier número perteneciente al rango NXY = 400 [...]»

Apartado Sexto:

> «La Comisión Nacional de los Mercados y la Competencia, los operadores y las empresas que realicen llamadas comerciales efectuarán las actuaciones necesarias [...] para que dicho rango de numeración esté plenamente operativo en el plazo de **6 meses** desde la entrada en vigor de la presente resolución.
>
> Una vez cumplido dicho plazo, **las llamadas comerciales sólo podrán efectuarse a través del rango NXY = 400 no pudiendo utilizarse desde entonces ningún otro rango de numeración para la realización de llamadas comerciales.**»

**Timeline: in force 17 April 2026 + 6 months ⇒ approximately 17 October 2026.**

### This directly and fatally contradicts the product concept — subject to one scope argument

The whole premise is "the SDR presents their **own existing** number." A 400 number is:

- **outbound-only** — it cannot receive calls at all (Segundo.1, Tercero.1);
- **not the rep's number** — it is a resource assigned by the CNMC to an operator and provided to the calling business;
- **not portable to the rep's identity** in any meaningful sense (Cuarto.2 provides for portability of 400 numbers between operators, not for turning a rep's mobile into one).

So from ~17 October 2026, for any caller in scope, "present the rep's own number" and "make a commercial call" become **mutually exclusive by construction**. No CLI configuration can satisfy both. This is a far more serious obstacle than anything in Orden TDF/149/2025, and it is not a blocking-probability problem — it is a categorical one.

### The one genuine argument that this does not bind a B2B SaaS — and it is a decent one

There is a **clear internal inconsistency** in the Resolution:

- **Primero.2 is scoped**: the exclusivity binds «las empresas comprendidas en el ámbito de aplicación de la citada Ley [10/2025]».
- **Sexto is unscoped**: «las llamadas comerciales sólo podrán efectuarse a través del rango NXY = 400».

The scope of Ley 10/2025 is narrow and explicitly consumer-facing. Art. 2.2:

> «2. Esta ley será de aplicación a las empresas y grupos de sociedades [...] que lleven a cabo la venta de bienes o la prestación de servicios diferentes a los recogidos en el apartado anterior en territorio español **destinados principalmente a personas consumidoras y usuarias** conforme al artículo 3 del Real Decreto Legislativo 1/2007 [...] siempre y cuando, en el ejercicio económico anterior, de forma individual o en el seno del grupo de sociedades del que formen parte, **hayan ocupado al menos a 250 personas trabajadoras, su volumen de negocios anual haya excedido de 50 millones de euros, o su balance de negocios anual haya excedido de 43 millones de euros**.»

Art. 2.1 separately catches providers of «servicios de carácter básico de interés general» (water, gas, electricity, passenger transport, postal, electronic communications, financial services) regardless of size.

Art. 1: «Esta ley tiene por objeto la regulación de los niveles mínimos de calidad [...] de las empresas que presten determinados servicios de carácter básico de interés general y de las grandes empresas.»

Art. 3.1 defines «Clientela» as «las personas consumidoras o usuarias [...]».

**A pure B2B SaaS company, below the 250-employee / €50M / €43M thresholds, selling to businesses rather than «personas consumidoras y usuarias», is outside Ley 10/2025 entirely.** On Primero.2's own terms, the 400-exclusivity therefore does not bind it. Its customers might be caught if they are large consumer-facing firms — but a B2B-to-B2B sales motion is not.

**Which paragraph wins is unresolved.** Primero.2 is the operative prohibition and carries the express statutory scope qualifier drawn from the enabling provision (Ley 10/2025 Art. 16.3, cited in the Resolution's closing words: «en cumplimiento de lo fijado en el artículo 16.3 Ley 10/2025»). Sexto reads as a deadline provision whose final sentence was drafted loosely. On ordinary principles the scoped operative provision should govern and Sexto should be read as shorthand for "in-scope commercial calls". **But Sexto is what a supervising authority reads first, and the CNMC is expressly charged with supervision (Cuarto.3: «La Comisión Nacional de los Mercados y la Competencia supervisará el cumplimiento de lo dispuesto en la presente resolución»).**

Note the interaction with Q3: **the scope arguments for Art. 9 and for the 400 regime point in opposite directions.** Art. 9 (Orden TDF/149/2025) has *no* scope qualifier and so probably catches B2B. The 400 exclusivity (Resolución 2026) has an *express* scope qualifier tied to a consumer-facing statute and so probably does not catch a small B2B seller. These are different instruments with different enabling provisions; there is no inconsistency in reaching different answers.

Also relevant, and independently significant for any product routing commercial traffic into Spain — **Ley 10/2025 Art. 16.4** creates a new operator blocking duty aimed squarely at commercial calls that do not use the designated code:

> «4. Deberán bloquearse por parte del operador que recibe la llamada las llamadas de servicios de comunicación vocal provenientes de números de tarifas especiales o inteligentes atribuidos a servicios distintos de los previstos en el apartado anterior.
>
> De igual modo, el operador que origina o reciba la llamada bloqueará por iniciativa propia, o cuando así sea solicitado por la autoridad competente, cualquier comunicación vocal dirigida desde un número de teléfono del que hubiera **indicios de originar llamadas comerciales sin código numérico específico** o sin cumplir con lo previsto en el apartado 1 del artículo 66 de la Ley 11/2022 [...]
>
> A tal efecto, los operadores deberán elaborar sistemas y procedimientos técnicos que permitan identificar de forma objetiva y razonable las llamadas comerciales identificadas en el párrafo anterior. **Su utilización requerirá autorización expresa mediante resolución motivada dictada por la Secretaría de Estado de Telecomunicaciones e Infraestructuras Digitales.**»

This is behaviour-based blocking on «indicios» — patterns indicating commercial calling from a non-400 number. It is not CLI-range-based and therefore is not evaded by choosing a geographic number. It requires prior SETID authorisation of the detection criteria (Disposición transitoria única.3 required operators to notify their criteria within one month of entry into force). **Note it applies to «el operador que origina o reciba la llamada» — without any Ley 10/2025 scope qualifier attached to the calls being blocked.** A high-volume outbound dialling pattern from a rep's mobile is exactly the signature such a system is designed to catch, whoever the callee is.

### CNMC / SETID guidance located

- **CNMC, Resolución sobre la asignación inicial de numeración del rango 400** — <https://www.cnmc.es/sites/default/files/6752256.pdf>. Confirms operational mechanics and, notably, that 400-range traffic is itself subject to the TDF/149/2025 blocking rules: «los operadores están obligados al cumplimiento de las medidas de bloqueo de llamadas con numeración 400 en una serie de supuestos: las recibidas del extranjero, o las que utilicen como identificador de llamada numeración no asignada o numeración propia no adjudicada a ningún cliente.» **So migrating to 400 does not escape Art. 5.1 for internationally-originated traffic.**
- **CNMC Circular 1/2026, de 18 de marzo** — Registro de Alias. SMS/MMS/RCS only; not relevant to voice CLI.
- I located **no** CNMC or SETID guidance interpreting the *scope* of «llamadas comerciales no solicitadas» in Art. 9, and none addressing geographic numbering under the Order.

---

## Q5 — Enforcement reality

The three layers must be kept apart. They are routinely conflated in the commentary and that conflation is what produced the original overstatement.

### (a) Legal prohibition on the caller

**Only Art. 9 (and, from ~Oct 2026, the 400 regime) prohibits anything at the caller level.** Arts. 4 and 5 impose **no duty on the caller whatsoever** — they are addressed exclusively to operators (Art. 2.1: «Las obligaciones establecidas en los capítulos II y III [...] se aplican a los operadores [...]»). This is the crux of the original error: presenting one's own number as CLI is not, in itself, prohibited conduct by Arts. 4 or 5. It is conduct that may cause an operator to drop the call.

Status: Art. 9 in force since 7 June 2025. Sanctionable under LGTel Art. 107.19 → Art. 109.1.c).

### (b) Blocking obligation on operators

| Provision | Duty | Effective from |
|---|---|---|
| Art. 4.1–4.3 | Block unattributed / unassigned / unallocated CLI | 7 March 2025 |
| Art. 4.4 | Block own-range CLI received in termination/transit | 7 March 2025 |
| Art. 5.1 | Block foreign-received calls bearing Spanish CLI | 7 June 2025 (DF 3.ª.2: «en el plazo máximo de tres meses desde su entrada en vigor») |
| Art. 7.1 | SMS analogue | 7 June 2025 |
| Arts. 7.2, 8 | Alias registry blocking | **15 September 2026** (delayed by Orden TDF/558/2026) |
| Ley 10/2025 Art. 16.4 | Behaviour-based commercial-call blocking | Requires prior SETID authorisation of criteria |

The **Orden TDF/558/2026, de 4 de junio** (<https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-12045>) delay of Arts. 7.2 and 8 to 15 September 2026 is itself the clearest official evidence of implementation difficulty. Its stated reason was avoiding wrongful blocking of legitimate traffic:

> «A fin de evitar la eventual generación de incidencias que pudieran derivar en el bloqueo indebido de alias legítimamente utilizados, con el consiguiente perjuicio tanto para los intereses de las entidades emisoras de dichos alias [...]»

That delay concerns messaging, **not voice**. The voice blocking duties in Arts. 4 and 5 were **not** delayed and have been live since March/June 2025.

### (c) What is actually enforced

**Evidence that Art. 5.1 blocking is real and biting:** the strongest indicator is the reaction of the Spanish contact-centre industry associations. Per *Relación Cliente* (<https://www.relacioncliente.es/boe-publica-bloqueo-llamadas-fraudulentas/>):

> «Desde la AEERC y la Asociación CEX apuntan que esto puede afectar muy negativamente a las empresas españolas que operan en offshore o nearshore, ya que su tráfico puede verse bloqueado. Si bien es cierto que la orden ministerial establece un mecanismo de excepción, este consiste en una solicitud justificada a la Secretaría de Estado de Telecomunicaciones e Infraestructuras [Digitales].»

Offshore/nearshore contact centres calling Spain with Spanish CLI is **structurally the same fact pattern as a CPaaS terminating Spanish traffic with a Spanish CLI.** The industry treated the risk as real enough to lobby about it. That is meaningful, though it is anticipatory concern rather than a post-hoc measurement.

**Published exceptions under Arts. 4.6 / 5.3: none located.** Both provisions provide:

> «Las excepciones se notificarán a la Comisión Nacional de los Mercados y la Competencia, y se publicarán en el portal de la Secretaría de Estado de Telecomunicaciones e Infraestructuras Digitales.»

I could not locate a published exception register on the SETID portal, nor any individual published exception resolution. **This is a negative finding and should be treated as such: absence of evidence in public search, not proof that none exists.** The exception route exists on paper; whether it is being used, and on what criteria, is not publicly visible. That opacity is itself a planning problem — you cannot assess whether a CPaaS-originated route would qualify.

**Art. 5.2 SETID resolution on irregular-traffic criteria: none located.** Art. 5.2 contemplates SETID-approved criteria for cases where roaming cannot be technically determined, and a future mandatory date for CLI-unverified marking. No such resolution found.

**CNMC sanctions under Art. 9: none located.** I found no CNMC or SETID sanctioning decision applying Art. 9 or LGTel Art. 107.19 to mobile-CLI commercial calling. Fourteen months after Art. 9 took effect, that is notable — though CNMC and SETID sanction files are not always promptly or fully published, so this is again a negative search result rather than a demonstrated nil return.

**Operator implementation of Art. 4.4 / 5.1 specifically:** no operator has published implementation detail, and there is no public data on block volumes. Disposición adicional primera requires annual blocked-call statistics to be filed with SETID and the CNMC («estadísticas de llamadas y mensajes bloqueados, desglosando, cuando sea técnicamente viable, el motivo del bloqueo») but I found no published aggregate. **The honest position is that implementation is asserted by the framework, corroborated indirectly by industry reaction, and unverified in public data.**

### Why "it works in production" and "it is legally exposed" are both true

- Arts. 4 and 5 are **network-layer** measures. They fail *silently and partially*. A call dropped by Art. 4.4 at a terminating operator is indistinguishable, from the SDR's console, from a prospect who did not answer. **No production telemetry will surface this as a compliance signal.** The stakeholder's evidence is real but measures the wrong thing.
- Art. 9 is a **conduct-layer** prohibition with no automatic technical enforcement. It bites only if someone complains and a regulator opens a file. Low observed enforcement is therefore entirely consistent with clear illegality.
- **The comparison to HubSpot does not establish legality.** It establishes that a large vendor ships the capability. Vendors commonly ship configurable CLI and place the compliance obligation on the customer by contract — which is exactly what Art. 2.3 does as a matter of law, since it binds «quienes realizan llamadas comerciales no solicitadas», i.e. the customer. The feature existing is fully consistent with the customer bearing the risk.

---

## Q6 — Honest bottom line

### Where you were wrong

1. **"Flatly prohibited by Orden TDF/149/2025" — overstated.** Arts. 4 and 5 impose **no obligation on the caller at all**. They are operator duties. The correct characterisation of Arts. 4/5 is *delivery risk*, not *illegality*.
2. **Art. 4.4 — your revised narrow reading is right,** and your original broad reading was wrong. It is a self-range integrity check, not a general anti-spoofing rule.
3. **Art. 5.1 — your revised reading is substantially right.** The duty is anchored to the international interconnect interface via Art. 2.2 and Art. 3.e). Domestic injection removes the trigger.
4. **The B2B carve-out from Art. 9 — this is where you are most likely wrong, and in the direction you did not want.** The premise that Art. 66.1.b) is consumer-scoped is incorrect: LGTel Anexo II ¶82–83 make *personas jurídicas* «usuarios finales». Art. 9 has no consumer qualifier and no definition of the operative term. Do not build on this.
5. **Geographic numbering — right about the Order, wrong about the current state of the law.** The Order is silent, but the April 2026 SETID Resolution has moved the goalposts entirely.

### Risk matrix

Split by numbering type and by prospect type. "Delivery" = probability of technical non-delivery. "Legal" = probability of enforcement action against the calling business.

| Scenario | Delivery risk (Arts. 4.4 / 5.1) | Legal risk (Art. 9) | 400-range risk (from ~17 Oct 2026) | Overall |
|---|---|---|---|---|
| **Own mobile, B2B prospecting** | Material, partial, silent — Art. 4.4 bites at CLI's home operator(s) and any transiting holder; Art. 5.1 systematic if routed via international interconnect | **Legally exposed, practically unenforced.** Textually caught; no located enforcement | Probably out of scope if the caller is a small B2B seller (Primero.2), but Sexto is unqualified and Ley 10/2025 Art. 16.4 behaviour-blocking has no scope qualifier | **Do not ship as default** |
| **Own mobile, B2C prospecting** | Same as above | **Clearly prohibited.** No scope argument survives. Compounded by AEPD/Art. 66.1.b) consent exposure and LOPDGDD Art. 23 Lista Robinson duties | Caught if the calling business is in Ley 10/2025 scope | **Do not do this** |
| **Own geographic landline, B2B** | Same Art. 4.4 / 5.1 delivery risk — these are **range-agnostic**; switching to 91x does not help | **Not prohibited by Art. 9.** Order is silent on geographic | **The live problem.** Sexto on its face bans all non-400 commercial CLI from ~17 Oct 2026; the Primero.2 scope argument is decent but untested | **Viable until ~Oct 2026; then contingent on the scope argument** |
| **Own geographic landline, B2C** | Same | Not prohibited by Art. 9 | Caught if in Ley 10/2025 scope | **Migrate to 400** |

### Statements I will stand behind

- **"Legally exposed but practically unenforced"** is the accurate description of **own-mobile CLI for B2B prospecting** today. Art. 9 catches it on the better reading; no enforcement located; no regulator has said either way. That is a real finding and it is the answer.
- **"Not prohibited, but unreliably delivered"** is the accurate description of **own-geographic CLI**, today.
- **"Structurally incompatible from ~17 October 2026, subject to a decent but untested scope argument"** is the accurate description of the whole "present the rep's own number" concept going forward. A 400 number cannot be a rep's own number. If Sexto governs, the product concept does not survive for commercial calls.
- **Neither Art. 4.4 nor Art. 5.1 is a range-selection problem.** Switching CLI from mobile to geographic changes the Art. 9 answer and changes nothing about Arts. 4 and 5. Anyone proposing "just use a landline number" as the fix has solved the wrong problem.

### What would actually resolve the open questions

None of these can be closed from public sources:

1. **A CNMC or SETID position on whether «llamadas comerciales no solicitadas» in Art. 9 reaches B2B.** This is the single highest-value unknown. A *consulta* to the CNMC would settle it.
2. **Whether the Art. 4.6 / 5.3 exception mechanism has ever been used, and on what criteria.** Nothing published; the register may not exist in practice.
3. **Whether Sexto or Primero.2 of the April 2026 Resolution governs for out-of-scope callers.** Worth a *consulta* before October.
4. **Actual block rates.** Only measurable empirically — instrument the product to distinguish network rejection (SIP 4xx/5xx at specific causes) from genuine no-answer, per terminating operator. Right now nobody, including the stakeholder, knows the real number, and the "it works in production" claim is unfalsifiable without it.
5. **The pre-amendment text of Primero.1.b) of the Resolución de 27 de mayo de 2013**, to confirm exactly what use of mobile ranges was withdrawn by DF segunda. Not verified here.

---

## Sources

**Primary**

- Orden TDF/149/2025, de 12 de febrero (consolidated) — <https://www.boe.es/eli/es/o/2025/02/12/tdf149/con> (BOE-A-2025-2870; BOE núm. 40, 15/02/2025; in force 07/03/2025; last consolidated update 05/06/2026)
- Orden TDF/558/2026, de 4 de junio (amends TDF/149/2025; delays Arts. 7.2 and 8 to 15/09/2026) — <https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-12045>
- Ley 11/2022, de 28 de junio, General de Telecomunicaciones (consolidated) — <https://www.boe.es/buscar/act.php?id=BOE-A-2022-10757> (Arts. 66.1, 107.19, 109, Anexo II ¶¶82–83, DF sexta.2)
- Real Decreto 424/2005, de 15 de abril (consolidated) — <https://www.boe.es/eli/es/rd/2005/04/15/424/con> (Arts. 61.2, 71, 81)
- AEPD Circular 1/2023, de 26 de junio — <https://www.boe.es/eli/es/cir/2023/06/26/1>
- Ley 10/2025, de 26 de diciembre, de servicios de atención a la clientela — <https://www.boe.es/eli/es/l/2025/12/26/10> (Arts. 1, 2, 3.1, 16, DT única)
- Resolución SETID de 14 de abril de 2026 (rango NXY=400) — <https://www.boe.es/buscar/act.php?id=BOE-A-2026-8409>
- Real Decreto 381/2015, de 14 de mayo (tráfico no permitido e irregular con fines fraudulentos) — cited in the Order's preamble as the enabling provision for Arts. 4 and 5
- Real Decreto 2296/2004, de 10 de diciembre (Arts. 27.7, 30, 34, 59) — numbering plan enabling provisions
- Ley Orgánica 3/2018 (LOPDGDD), Arts. 19 and 23 — via Circular 1/2023 Arts. 4 and 5

**Regulatory / secondary**

- CNMC, Resolución sobre la asignación inicial de numeración del rango 400 — <https://www.cnmc.es/sites/default/files/6752256.pdf>
- CNMC Circular 1/2026, de 18 de marzo (Registro de Alias) — via <https://www.iberley.es/noticias/la-cnmc-refuerza-lucha-fraude-comunicaciones-36260>
- AEERC / Asociación CEX concerns on offshore/nearshore blocking — <https://www.relacioncliente.es/boe-publica-bloqueo-llamadas-fraudulentas/>
- Bird & Bird — <https://www.twobirds.com/es/insights/2025/spain/llamadas-comerciales-bajo-regulación>
- Baker Tilly — <https://www.bakertilly.es/publicaciones/nueva-normativa-para-comunicaciones-empresariales-y-fraude-telefonico>
- Legitec — <https://legitec.com/nueva-prohibicion-de-llamadas-comerciales-desde-moviles-lo-que-debes-saber-sobre-la-orden-tdf-149-2025/>
- Enreach — <https://enreach.es/blog/como-afecta-la-orden-tdf1492025-a-las-llamadas-y-sms-de-tu-empresa/>
- Sinologic (400 range analysis) — <https://www.sinologic.net/en/2026-04/prefix-400-for-commercial-calls-in-spain-requirements-deadlines-and-how-it-affects-users-and-operators-boe-2026.html>
- PwC Periscopio Fiscal y Legal (Ley 10/2025 scope) — <https://periscopiofiscalylegal.pwc.es/ley-10-2025-de-26-de-diciembre-por-la-que-se-regulan-los-servicios-de-atencion-a-la-clientela/>

**Not legal advice.** Consolidated BOE texts carry the disclaimer «Este texto consolidado es de carácter informativo y no tiene valor jurídico»; for legal purposes the official publication governs. Confirm with Spanish telecoms counsel before shipping.
