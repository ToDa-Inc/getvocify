# WhatsApp Meta Copilot (contact-first)

**Date:** 2026-09-15  
**Status:** Ready for implementation  
**Repos:** getvocify (product). signalcore-backend is transport reference only.

## Decision

Do not port `MetaWhatsAppService` from signalcore-backend. That class routes **template vs session text** for a conversational sales agent (Redis 24h window, WABA templates, lead/strategy). It has no session interactive buttons or list messages.

Vocify already has the right layer: `backend/app/services/whatsapp/client.py` (Graph `v21.0`, same as Signalcore’s `MetaWhatsAppClient`). Grow that client. CRM writes stay in-process (`build_preview`, `approve_memo_core`, `HubSpotSearchService`) — the same contracts as `POST /memos/{id}/preview` and `POST /memos/{id}/approve`. No `/whatsapp/*` REST API.

Unipile cannot send Cloud API quick replies. Keep it as numbered-text fallback with the same action ids. Product path is Meta.

Signalcore may keep owning the Meta **webhook subscription** and forward the raw body to `POST /webhooks/whatsapp`. Vocify is the only sender of session replies for Vocify user phones. If Signalcore’s agent also replies on those numbers, disable that fan-out in signalcore (separate PR). Do not block Vocify work on it: inbound from a rep is always inside the 24h session window.

## Product

Contact-first, same as `chrome-extension/lib/review-targets.js`. Company rides with the contact. Deal is opt-in (`skip_deal`). Note + tasks write on approve. HubSpot Lists, call outcomes, and Signalcore-style chat are out of v1.

Copy: only real diffs (`visibleCrmUpdates` rules) + dated tasks + one target line. No essay summary on WhatsApp.

Primary Meta buttons (ids, not `1`/`2`/`3`):

| id | title | effect |
|---|---|---|
| `act:approve` | Actualizar | `approve_memo_core` |
| `act:keep` | No actualizar | `POST /memos/{id}/reject` equivalent |
| `act:retarget` | Cambiar deal | list: skip deal / matches / new deal / type a name |

Natural language in `waiting_approval` maps to the same actions (“quita el deal”, “otro deal”, “el de Acme”).

Split: long briefing as `type=text` (4096, split on blank lines). Interactive body stays short (≤1024, target ~280).

## API contracts (existing)

- `POST /webhooks/whatsapp` — only public ingress
- `POST /api/v1/memos/{id}/preview` — add `skip_deal`; when true, do **not** rehydrate `memos.hubspot_deal_id`
- `GET /api/v1/crm/hubspot/search/deals?q=` — deal picker / NL search
- `GET /api/v1/crm/hubspot/search/contacts?q=` — NL contact retarget
- `POST /api/v1/memos/{id}/approve` — already has `skip_deal`, `contact_id`, `deal_id`
- `POST /api/v1/memos/{id}/reject` — keep CRM as-is

WhatsApp processor calls the same Python functions those routes use. No HTTP self-calls.
