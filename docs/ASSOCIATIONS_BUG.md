# The `get_associations` parsing bug (Dec 2025 - Aug 2026)

If something about matching, contact resolution, or association-based lookups
behaves strangely and none of the obvious explanations hold, check whether it
predates `4df0c6b` (2026-08-14). Between late December 2025 and that fix,
`HubSpotAssociationService.get_associations()` - the single function backing
every "find the deals/contacts/companies associated with this object" lookup
in the backend - silently returned wrong results for every call, in two
different ways across two periods. This document is the postmortem, written
immediately after the fix while the investigation was still fresh, so a
future strange symptom can be checked against it instead of re-discovered
from scratch.

## What was actually wrong

`GET /crm/v4/objects/{objectType}/{objectId}/associations/{toObjectType}`
returns each associated object as `{"toObjectId": "...", "associationTypes":
[...]}` - `toObjectId` sits directly on the result item. Confirmed against
HubSpot's own OpenAPI schema (`MultiAssociatedObjectWithLabel`, `required:
[associationTypes, toObjectId]`), not assumed.

The parser never checked that key, in either of its two historical versions:

| Period | Commit | What the parser checked | Effect |
|---|---|---|---|
| 2025-12-31 - 2026-02-20 (~7 weeks) | `2344614` | `result.get("id", "")` | Never matches (real key is `toObjectId`) - but the default `""` means the returned list has the **same length** as the real associations, filled with empty-string IDs. Callers that treat a non-empty list as "found" (`if contact_ids:`) took the true branch, then tried to fetch/update an object with id `""` - a shape of failure much more likely to raise a visible error than to degrade silently. |
| 2026-02-20 - 2026-08-14 (~5.9 months) | `eb6669c` | `result.get("objectId") or result.get("id")`, then `result.get("to", [])[].get("toObjectId")` | Neither matches `toObjectId` on the result item directly. Every call returns a clean `[]` - indistinguishable from a real "no associations" result. This is the version that did the most damage, because it looks correct. |
| 2026-08-14 onward | `4df0c6b` | `result.get("toObjectId")` first, old checks kept as fallback | Matches the real shape. |

`eb6669c`'s own diff shows the intent was to fix the first (visibly broken)
version - the author noticed `result.get("id", "")` was wrong and replaced it
with a guess about "two HubSpot v4 formats," without a real response to
verify against. The guess was also wrong, and worse: it turned a loud bug
into a silent one.

## Every call site, what it resolved, and what degraded

All 15 call sites go through the same function and the same underlying HTTP
call - this was never deal-specific.

| # | Site | Resolved | Silent effect | Was it noticed? |
|---|---|---|---|---|
| 1 | `contact_identity.py` `_company_for_contact` | A matched contact's company, for every branch of `resolve_identity`'s cascade | `company_id` always `None` from this path | No - no exception, no log, nothing visibly wrong |
| 2 | `contact_identity.py` `_deal_matches_for_contact` | A matched contact's deals, same cascade | `deal_matches` always `[]` -> "Contact only (no deal)" for every contact with a deal, in every account | Yes, eventually - first blamed on an unrelated pipeline filter (see git history around 2026-08-14) before this was found underneath it |
| 3 | `sync.py:484` | The existing deal's real contact, to update it instead of creating a new one | Falls through to `contacts.create_or_update()`, which without a fresh email in that call can create a **new** HubSpot contact and associate it to the same deal (`sync.py:855`) - see "Connection to the duplicate-contact report" below | No - the fallback's own success log looks identical to the legitimate "no contact existed yet" case |
| 4 | `sync.py:717` | Same, when extraction has only name/role/phone (no email, so `create_or_update` can't run) | The whole update step is skipped, no exception, no log | No |
| 5 | `sync.py:762` | The existing deal's associated company, to patch fields | Same silent skip - company field updates from the call never applied | No |
| 6 | `crm.py:353` (`/contacts/{id}/context`) | A contact's company, for the extension's session vocab when recording from a contact page | `companyId` always `null` in the context sent to the popup | No |
| 7 | `crm.py:402` (`/companies/{id}/context`) | A company's contacts, for the "multiple contacts" picker when recording from a company page | Picker never populates, even for a company with many contacts | Only if someone specifically tested recording from a company page |
| 8 | `crm.py:1243` / `crm.py:1249` (`/deals/{id}/context`) | A deal's company and contact, for page-context enrichment when recording from a deal page | `companyId`/`contactId`/`contactName`/`contactEmail` always `null` in `dealCtx` - the deal itself still resolves correctly (it comes from the URL, not this call), but its contact never arrives as an "explicit" pick | No - this was believed to work correctly until this investigation; see correction below |
| 9 | `preview.py` (4 call sites) | The selected deal's company/contact name, purely for display under "Deal Target" in the preview | Blank company/contact fields under an otherwise-correct deal name | Cosmetic, easy to overlook |
| 10 | `matching.py:204` (`_find_by_company_association`, Strategy 1 of legacy `find_matching_deals`) | Deals associated to a company found by name | Always contributed zero matches | Partially - this is the one site with an explicit count log (`Match: company %s -> %d deal associations`), but it was masked by Strategy 2 succeeding independently (see below) |
| - | `matching.py` Strategy 0 (`resolve_contact_anchor`, reuses site #2) | Deals linked to an email-matched contact | Same as #2 - always zero | No |

**Correction to a conclusion reached earlier in the same investigation**: recording
from a HubSpot deal page was believed to correctly surface that deal's contact as
an "explicit page-context pick" (`preferred_contact_id`), the same way a contact
page does. That conclusion checked the *wiring* (the deal's contact ID does flow
from `dealCtx.contactId` into `preferred_contact_id` if it's non-null) but not
whether `dealCtx.contactId` itself ever got populated - it never did (site #8).
Recording from a deal page never gave an explicit contact pick; it silently fell
back to the generic email/phone/name cascade instead. The deal itself was never
affected (it comes from the URL, not from this lookup).

## What masked it for this long

Two independent coincidences, not one:

1. **Deal matching had a fallback that doesn't need associations.**
   `_find_by_company` (Strategy 2) matches by plain text: exact `"{company}
   Deal"` first, then any deal whose `dealname` contains the company name as
   a substring. Neither depends on `get_associations`. As long as a deal's
   name happened to mention its company - guaranteed for the app's own
   naming convention, common by habit for manually-created deals too - deal
   matching still produced a result, even though two of its three
   strategies were contributing nothing. For a client whose deal-naming
   habits don't mention the company at all, this fallback also fails, and
   there was no working path left - see the correction to the "only
   app-created deals worked" theory above.
2. **A deterministic placeholder email created accidental contact dedup.**
   `HubSpotContactService.create_or_update()` generates a placeholder email
   from the contact's name (`{slug}@lead.getvocify.com`) when no real email
   is dictated. If a sales rep said a contact's name the same way across
   multiple calls on the same deal, the placeholder matched by email lookup
   and updated the same (duplicate) contact each time, instead of creating a
   new one per call. The visible symptom was "one duplicate contact coexists
   with the real one," not "a new duplicate every single call" - much less
   alarming, easy to attribute to something else.

Contributing factor, not a cause on its own: logging discipline was
inconsistent across call sites. Site #10 had a real count in the logs the
whole time (`0 deal associations`) and it still went unnoticed - a log that
nobody is specifically looking for doesn't help. Sites #3-9 had no log at all
for the degraded path, only for outcomes that look identical to a correct
result.

## Connection to the customer-reported duplicate-contact issue

The customer post-mortem describing "creates duplicate contacts instead of
associating existing ones" had been attributed to the deal-first architecture
in general. Site #3 above is a confirmed, code-level path to exactly that
symptom: an existing deal's real contact was never found (this bug), so the
sync fell through to creating a new contact, which then got associated to
that same deal (`sync.py:855`) alongside the original. This is not proven to
be the *only* cause of every reported instance, but it is a real, previously
unidentified one. Re-check with a real case now that the fix is deployed
before considering that report fully explained.

## Fix and regression coverage

- Fixed in `4df0c6b` (2026-08-14): `toObjectId` checked first, matching
  HubSpot's real schema. Old checks kept as a defensive fallback only.
- `backend/tests/hubspot/test_associations.py`: characterization test
  against the exact real response shape (no network) - the kind of test that
  would have caught this on day one.
- `associations.py` now logs at `ERROR` when HubSpot returns results but none
  match a known id field - the specific signature of this bug class, so a
  future parser mismatch can't hide behind a normal-looking empty list again.

## Open question this raises for the rest of this session's work

FASE 2's debt (`docs/VERIFY_CONTACT_FIRST_NOTES.md`, sections 11.A-11.D:
the `track()` race condition, the `in_flight` design, the partial unique
index, the CASCADE-on-disconnect issue) was designed and reasoned about
while this bug was live. None of those designs are wrong on their own
terms, but some of the *symptoms* they were built to explain may have had
this as a contributing or root cause instead. Before adding any of that
debt to a build queue, re-verify what's still actually broken with
associations now working correctly.
