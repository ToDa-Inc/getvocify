# Pipedrive CRM adapter — Phase 0+1 plan

**Date:** 2026-09-16  
**Spec:** `docs/superpowers/specs/2026-09-16-pipedrive-crm-adapter-design.md`  
**Branch:** `feat/pipedrive-crm-adapter`  
**Playbook:** `backend/app/services/salesforce/`

Same-release ship: OAuth + schema + identity + preview + memo sync + Settings + search routing. No CallLogs, no Chrome, no `hubspot_*` writes, no invented deal URL.

## Files

New: `backend/app/services/pipedrive/*`, `crm_providers/pipedrive_provider.py`, `api/crm_pipedrive.py`, `models/pipedrive_crm.py`, Settings/Pipedrive UI, `src/lib/api/pipedrive-setup.ts`, `backend/tests/pipedrive/*`.

Touch only: `factory.py`, `api/router.py`, `config.py`, `logging_config.py`, `extraction_context.py` (GET-by-`matched_deal_id`), `whatsapp/processor.py` (`_crm_display_name`), `src/lib/api/crm.ts` (no HubSpot fallthrough), `SettingsPage.tsx`, `CRM_PROVIDER_CONFIGS`, `.env.example`.

## Locks

- v2: deals/persons/orgs/search/fields/pipelines/stages/activities. v1: notes, users, activityTypes, OAuth.
- Token TTL = response `expires_in`. Store `metadata.api_domain`.
- Scopes on the Marketplace app: `deals:full contacts:full activities:full search:read users:read`.
- Identity → `IdentityResolution` + `ContactAnchor`. Cascade copied from HubSpot.
- Persist deal id on `memos.matched_deal_id` only.
- Call outcomes all false; `call_outcome` → `CALL_OUTCOME_UNSUPPORTED`.
- Missing task type → `tasks_warning`. Missing stage on create → `PIPEDRIVE_STAGE_REQUIRED`.
- Search `q` trim; length < 2 → `[]`.

## Verify

`pytest backend/tests/pipedrive` plus existing HubSpot/Salesforce/WhatsApp CRM tests. Settings: Reticle if a session is connected; otherwise say so.
