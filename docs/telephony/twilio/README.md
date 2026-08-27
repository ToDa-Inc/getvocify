# Twilio reference

Twilio is the carrier we ship on. Decision to stay is in [../DECISION.md](../DECISION.md).

| Document | What it covers |
|---|---|
| [assumption-audit.md](assumption-audit.md) | Adversarial audit of the seven assumptions the shipped implementation rests on, each marked CONFIRMED / REFUTED / DOCS SILENT / UNVERIFIABLE against primary sources |
| [`../../runbooks/twilio-setup.md`](../../runbooks/twilio-setup.md) | Operational setup: console configuration, HubSpot recording endpoint registration, local development, cost model |

## Audit results in brief

| # | Assumption | Verdict |
|---|---|---|
| A1 | Verified Caller ID works for non-US numbers | **DOCS SILENT** — no country restriction documented anywhere. The "US-only" claim is unsourced folklore; the real cause in community reports was Geo Permissions plus the trial 5-number cap |
| A2 | Transit Caller ID sunset, Verified Caller ID is the replacement | **Substance right, date wrong.** 2026-06-22 per Twilio's changelog, not the 2026-05-31 from a third-party article. Already past — audit production logs |
| A3 | Account need not be Spanish to present a Spanish CLI | Account registration is not the constraint. Twilio's "For domestic calls, please use a Twilio phone number" sits under **Outbound requirements** — conditions that must be met, not a best practice |
| A4 | Spanish mobile CLI restricted for commercial calls | **CONFIRMED, and worse than assumed.** Two articles of TDF/149/2025 each independently break BYO-CLI, neither with an ownership exception. See [the regulatory analysis](../regulatory/spain-cli-tdf149-2025.md) |
| A5 | Dual-channel recording bills 1×, not 2× | **CONFIRMED** — $0.0025/min. Caveat: storage rounds each recording up to a full minute, which dominates the line at SDR call-duration distributions |
| A6 | No practical cap on Verified Caller IDs per account | **DOCS SILENT** for upgraded accounts. Trial is 5, documented as lifted on upgrade, without saying to what. A real scaling risk for a product where every SDR registers a number |
| A7 | Webhook signature validation depends on the request URL | **CONFIRMED** — rebuilding from a configured public base URL is correct. Watch: query strings are signed, `bodySHA256` arrives as a param, and port handling varies by scheme so TLS-terminating proxies are the classic trap |

The consequential one is A4. A1 was the assumption we most feared and it turned out not to be
our problem at all — which is worth remembering, because we nearly migrated carriers on the
strength of a single unsourced forum answer.
