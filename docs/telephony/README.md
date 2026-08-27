# Telephony reference

Carrier research, regulatory analysis, and the carrier decision for Vocify outbound calling.

**Start here:** [DECISION.md](DECISION.md) — the verdict, the comparison, the caveats, and the
list of assumptions that turned out to be false.

**If you only read one other thing:** [Spain caller ID law](regulatory/spain-cli-tdf149-2025.md).
It is the reason the outbound calling design has to change, and it applies to every carrier
equally.

## Verdict in four lines

Stay on Twilio — the Spanish caller-ID problem is national law, not a Twilio limitation, so
switching carriers changes nothing. But stop trying to be the carrier in Spain: from
**2026-10-17** commercial calls may only originate from the new **400** range, which is
operator-held and cannot receive calls, so "present your own number" becomes impossible.
Capture the audio at the endpoint instead — we already have most of that technology, and it has
no telephony-regulation exposure at all.

## Contents

| Document | What it covers |
|---|---|
| [DECISION.md](DECISION.md) | The decision, ranked options, side-by-side comparison, caveats, edge cases, false assumptions |
| [regulatory/spain-cli-tdf149-2025.md](regulatory/spain-cli-tdf149-2025.md) | The law read against our design, from BOE primary sources — including the 400-range deadline |
| [regulatory/legal-scope-analysis.md](regulatory/legal-scope-analysis.md) | Article-by-article scope analysis with verbatim Spanish quotes; corrects two of our overstatements |
| [regulatory/hubspot-calling-precedent.md](regulatory/hubspot-calling-precedent.md) | What HubSpot actually ships. It built the same feature on Twilio and documents that Spain fails |
| [portability/carrier-coupling-audit.md](portability/carrier-coupling-audit.md) | What in the codebase is Twilio-coupled, with line counts and the real migration cost |
| [twilio/](twilio/) | Twilio reference — including an adversarial audit of the assumptions we shipped on |
| [telnyx/](telnyx/) | Telnyx reference — caller ID, WebRTC in MV3, recording, pricing, multi-tenancy |

Operational setup for the shipped Twilio integration lives in
[`../runbooks/twilio-setup.md`](../runbooks/twilio-setup.md). The implementation plan that
produced the current code is
[`../superpowers/plans/2026-08-26-vocify-outbound-calling.md`](../superpowers/plans/2026-08-26-vocify-outbound-calling.md)
— note that several of its stated assumptions are now known to be false; see the table at the
end of [DECISION.md](DECISION.md).

## How to read the research documents

The four Telnyx documents and the Twilio assumption audit were produced under a strict rule:
**every claim is tagged either DOCUMENTED with a URL, VERIFIED BY INSPECTION with command
output, or NOT DOCUMENTED.** "NOT DOCUMENTED" is a finding, not a gap in the research — it
means the vendor does not publish it and we would have to test it or ask.

Do not silently upgrade a NOT DOCUMENTED claim to a fact because it seems reasonable. Several
of the most expensive mistakes in this area came from exactly that.

Currency of the research: fetched 2026-08-27. Vendor pricing and policy pages change without
notice. Re-verify any figure before it enters a customer-facing model or a contract.
