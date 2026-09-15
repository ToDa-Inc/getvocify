# WhatsApp Meta Copilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Vocify WhatsApp a Meta Cloud API copilot: contact-first preview, split text, three native buttons (update / keep / change deal), list+NL to pick or reset a deal, then the existing HubSpot approve path.

**Architecture:** Grow `WhatsAppClient` (Graph v21.0 session messages) with list payloads copied from Meta’s interactive schema, not from signalcore-backend’s `MetaWhatsAppService` (templates + 24h Redis + agent chat). Parser accepts `button_reply` and `list_reply`. Processor stays a state machine and calls `build_preview` / `approve_memo_core` / HubSpot search in-process. Unipile only mirrors the same action ids as numbered text.

**Tech Stack:** FastAPI, httpx, pytest (`cd backend && python -m pytest … -v`), existing Supabase `conversations` row, HubSpot search already in `app/services/hubspot/search.py`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-15-whatsapp-meta-copilot-design.md`
- Do not copy `signalcore-backend/shared/integrations/meta/meta_whatsapp_service.py`.
- Do not add `/api/v1/whatsapp/*` routes. Ingress remains `POST /webhooks/whatsapp`.
- Do not HTTP-call Vocify from Vocify; call the same functions the memo/CRM routes use.
- Interactive body ≤ 1024 chars; button title ≤ 25; list button ≤ 20; list ≤ 10 rows; text messages ≤ 4096.
- Action ids are `act:approve`, `act:keep`, `act:retarget`, `pick:skip_deal`, `pick:new_deal`, `pick:deal:{id}`, `pick:type_name`. Never `1`/`2`/`3` as ids.
- Copy shows only diffs that `visibleCrmUpdates` would show (no identity noise, no empty, no task rows in the field list) plus dated tasks plus one target line.
- Default preview is contact-first `skip_deal=true` unless the user picked a deal this turn.
- `skip_deal=true` on preview must not rehydrate `memos.hubspot_deal_id`.
- Unipile remains text-only fallback; do not pretend it has native buttons.
- HubSpot Lists, call outcomes, and Signalcore agent replies are out of this plan.

## File map

- Create: `backend/app/services/whatsapp/split.py` — split text on blank lines, cap 4096
- Create: `backend/app/services/whatsapp/copy.py` — target line + diffs + tasks
- Create: `backend/app/services/whatsapp/actions.py` — id helpers and list sections
- Create: `backend/migrations/034_whatsapp_retarget_states.sql` — conversation states
- Create: `backend/tests/whatsapp/test_webhook_parser.py`
- Create: `backend/tests/whatsapp/test_client_interactive.py`
- Create: `backend/tests/whatsapp/test_split.py`
- Create: `backend/tests/whatsapp/test_copy.py`
- Create: `backend/tests/whatsapp/test_actions.py`
- Create: `backend/tests/whatsapp/test_intent.py`
- Create: `backend/tests/whatsapp/test_preview_skip_deal.py`
- Create: `backend/tests/whatsapp/test_processor_retarget.py`
- Modify: `backend/app/services/whatsapp/webhook_parser.py` — `list_reply`
- Modify: `backend/app/services/whatsapp/client.py` — `send_interactive_list`; keep button body short
- Modify: `backend/app/services/whatsapp/processor.py` — send card + retarget; stop stuffing preview into button body
- Modify: `backend/app/services/unipile/client.py` — footer matches Meta ids
- Modify: `backend/app/services/conversation/intent.py` — skip_deal / change_deal / keep
- Modify: `backend/app/models/conversation.py` — new states
- Modify: `backend/app/models/approval.py` — `PreviewRequest.skip_deal`
- Modify: `backend/app/services/preview_targets.py` — honor `skip_deal`
- Modify: `backend/app/api/memos.py` — GET/POST preview `skip_deal`

---

### Task 1: Parse Meta `list_reply`

**Files:**
- Modify: `backend/app/services/whatsapp/webhook_parser.py`
- Test: `backend/tests/whatsapp/test_webhook_parser.py`

**Interfaces:**
- Consumes: Meta webhook `messages[].interactive.type = list_reply | button_reply`
- Produces: `IncomingMessage.type="button"` with `button_id` / `button_title` for both (processor already treats button as an id)

- [ ] **Step 1: Write the failing test**

```python
from app.services.whatsapp.webhook_parser import parse_webhook

def _interactive(kind, inner):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [{
            "id": "wamid.1",
            "from": "34600111222",
            "timestamp": "1",
            "type": "interactive",
            "interactive": {"type": kind, kind: inner},
        }]}}]}],
    }

def test_parses_button_reply():
    msgs = parse_webhook(_interactive("button_reply", {"id": "act:approve", "title": "Actualizar"}))
    assert len(msgs) == 1
    assert msgs[0].type == "button"
    assert msgs[0].button_id == "act:approve"

def test_parses_list_reply():
    msgs = parse_webhook(_interactive("list_reply", {"id": "pick:skip_deal", "title": "Sin deal"}))
    assert msgs[0].button_id == "pick:skip_deal"
    assert msgs[0].type == "button"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/whatsapp/test_webhook_parser.py::test_parses_list_reply -v`

Expected: FAIL (`list_reply` ignored → empty list)

- [ ] **Step 3: Write minimal implementation**

In `parse_webhook`, after the `button_reply` branch, handle `interactive.get("type") == "list_reply"` the same way (`id`/`title` from `list_reply`). Keep `type="button"` so the processor does not grow a fourth inbound type.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/whatsapp/test_webhook_parser.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/whatsapp/webhook_parser.py backend/tests/whatsapp/test_webhook_parser.py
git commit -m "$(cat <<'EOF'
feat(whatsapp): parse Meta list_reply as button ids

EOF
)"
```

---

### Task 2: Meta list send + text split

**Files:**
- Modify: `backend/app/services/whatsapp/client.py`
- Create: `backend/app/services/whatsapp/split.py`
- Test: `backend/tests/whatsapp/test_client_interactive.py`
- Test: `backend/tests/whatsapp/test_split.py`

**Interfaces:**
- Consumes: `to: str`, `body: str`, `button_text: str`, `sections: list[dict]` with `{title, rows:[{id,title,description?}]}`
- Produces: Graph POST `{phone_number_id}/messages` with `interactive.type=list`; `split_text(text) -> list[str]` each ≤ 4096

- [ ] **Step 1: Write the failing tests**

```python
from app.services.whatsapp.split import split_text

def test_split_keeps_short_text():
    assert split_text("hola") == ["hola"]

def test_split_on_blank_lines_when_over_limit():
    a = "A" * 3000
    b = "B" * 3000
    parts = split_text(a + "\n\n" + b)
    assert len(parts) == 2
    assert all(len(p) <= 4096 for p in parts)
```

```python
import json
import respx
import httpx
from app.services.whatsapp.client import WhatsAppClient

@respx.mock
async def test_send_interactive_list_payload():
    client = WhatsAppClient()
    client.access_token = "t"
    client.phone_number_id = "pn"
    route = respx.post("https://graph.facebook.com/v21.0/pn/messages").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.x"}]})
    )
    await client.send_interactive_list(
        "+34600",
        "Elige deal",
        "Cambiar",
        [{"title": "Deal", "rows": [{"id": "pick:skip_deal", "title": "Sin deal"}]}],
    )
    payload = json.loads(route.calls[0].request.content)
    assert payload["type"] == "interactive"
    assert payload["interactive"]["type"] == "list"
    assert payload["interactive"]["action"]["button"] == "Cambiar"
    assert payload["interactive"]["action"]["sections"][0]["rows"][0]["id"] == "pick:skip_deal"
```

If the suite does not already use `respx`, mock `httpx.AsyncClient.post` with `unittest.mock.AsyncMock` instead — do not add a dependency.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/whatsapp/test_split.py tests/whatsapp/test_client_interactive.py -v`

Expected: FAIL (module / method missing)

- [ ] **Step 3: Write minimal implementation**

`split_text`: if `len(text) <= 4096` return `[text]`; else split on `\n\n`, greedily pack paragraphs, never cut a paragraph unless one paragraph itself is > 4096 (then hard-slice).

`WhatsAppClient.send_interactive_list`: same headers/URL as `send_interactive_buttons`. Truncate body 1024, button 20, ≤10 rows, row title 24, description 72, id 200. `to` without leading `+` (existing client behavior).

Extract the shared POST-to-messages helper if both send methods duplicate the httpx block; do not invent a service class.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/whatsapp/test_split.py tests/whatsapp/test_client_interactive.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/whatsapp/client.py backend/app/services/whatsapp/split.py backend/tests/whatsapp/test_split.py backend/tests/whatsapp/test_client_interactive.py
git commit -m "$(cat <<'EOF'
feat(whatsapp): Meta list messages and text split

EOF
)"
```

---

### Task 3: Copy + action ids

**Files:**
- Create: `backend/app/services/whatsapp/copy.py`
- Create: `backend/app/services/whatsapp/actions.py`
- Test: `backend/tests/whatsapp/test_copy.py`
- Test: `backend/tests/whatsapp/test_actions.py`

**Interfaces:**
- Consumes: `ApprovalPreview` (or a duck with `selected_contact`, `selected_deal`, `skip_deal`, `proposed_updates`, extraction nextSteps)
- Produces: `briefing_text(preview) -> str`, `button_body(preview) -> str` (must be ≤ 280 chars in tests), `primary_buttons() -> list[dict]`, `deal_list_sections(matches, has_deal) -> list[dict]`

Port filter rules from `chrome-extension/lib/review-insights.js` `visibleCrmUpdates` / `IDENTITY_NOISE`. Do not import JS.

- [ ] **Step 1: Write the failing tests**

```python
from app.services.whatsapp.copy import briefing_text, button_body
from app.services.whatsapp.actions import PRIMARY_BUTTONS, deal_list_sections, ACT_APPROVE, ACT_KEEP, ACT_RETARGET, PICK_SKIP_DEAL

def test_copy_hides_unchanged_email_and_empty_fields():
    preview = type("P", (), {
        "selected_contact": type("C", (), {"name": "Ana López", "company_name": "Neurtek"})(),
        "selected_deal": None,
        "skip_deal": True,
        "proposed_updates": [
            {"object_type": "contacts", "field_name": "email", "field_label": "Email", "new_value": "a@b.com", "current_value": "a@b.com"},
            {"object_type": "contacts", "field_name": "jobtitle", "field_label": "Cargo", "new_value": "Directora", "current_value": ""},
        ],
    })()
    text = briefing_text(preview, next_steps=["Llamar a Aritzel"])
    assert "Ana López" in text
    assert "Cargo" in text
    assert "a@b.com" not in text
    assert "Llamar a Aritzel" in text
    body = button_body(preview)
    assert len(body) <= 280
    assert "deal" not in body.lower() or "solo" in body.lower()

def test_primary_buttons_are_semantic():
    ids = [b["id"] for b in PRIMARY_BUTTONS]
    assert ids == [ACT_APPROVE, ACT_KEEP, ACT_RETARGET]
    assert all(len(b["title"]) <= 25 for b in PRIMARY_BUTTONS)

def test_deal_list_includes_reset_and_caps_rows():
    matches = [{"deal_id": str(i), "deal_name": f"Deal {i}"} for i in range(12)]
    sections = deal_list_sections(matches, has_deal=True)
    rows = [r for s in sections for r in s["rows"]]
    assert any(r["id"] == PICK_SKIP_DEAL for r in rows)
    assert sum(len(s["rows"]) for s in sections) <= 10
```

Use real `ProposedUpdate` models if constructing `type()` ducks is brittle; keep the assertions.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/whatsapp/test_copy.py tests/whatsapp/test_actions.py -v`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`actions.py` constants + `PRIMARY_BUTTONS` titles in Spanish: `Actualizar`, `No actualizar`, `Cambiar deal`. List rows: `Sin deal`, up to 7 matches as `pick:deal:{id}`, `Deal nuevo` (`pick:new_deal`), `Escribe el nombre` (`pick:type_name`). If `has_deal` is false, still include `Sin deal` as the current state (idempotent).

`copy.py`: one line `*{contact}* · {company}` plus `Solo contacto` or `Deal · {name}`. Then tasks. Then grouped diffs Contacto / Empresa / Deal (omit Deal group when `skip_deal`). `button_body`: target line + `¿Actualizo HubSpot?` + counts (`1 tarea · 2 campos`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/whatsapp/test_copy.py tests/whatsapp/test_actions.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/whatsapp/copy.py backend/app/services/whatsapp/actions.py backend/tests/whatsapp/test_copy.py backend/tests/whatsapp/test_actions.py
git commit -m "$(cat <<'EOF'
feat(whatsapp): contact-first copy and semantic action ids

EOF
)"
```

---

### Task 4: `skip_deal` on preview (reset deal)

**Files:**
- Modify: `backend/app/models/approval.py` (`PreviewRequest`)
- Modify: `backend/app/services/preview_targets.py`
- Modify: `backend/app/api/memos.py` (GET and POST preview)
- Test: `backend/tests/whatsapp/test_preview_skip_deal.py`

**Interfaces:**
- Consumes: `skip_deal: bool` on GET query and POST body
- Produces: `resolve_preview_deal_selection(..., skip_deal=False) -> (None, False)` when skip_deal is true, ignoring memo `hubspot_deal_id`

- [ ] **Step 1: Write the failing test**

```python
from app.services.preview_targets import resolve_preview_deal_selection

def test_skip_deal_wins_over_existing_deal_id():
    selected, create_new = resolve_preview_deal_selection(
        deal_id="123",
        create_new_deal=False,
        has_selected_contact=True,
        has_contact_candidates=False,
        skip_deal=True,
    )
    assert selected is None
    assert create_new is False

def test_omit_deal_with_contact_still_skips():
    selected, create_new = resolve_preview_deal_selection(
        deal_id=None,
        create_new_deal=False,
        has_selected_contact=True,
        has_contact_candidates=False,
        skip_deal=False,
    )
    assert selected is None
    assert create_new is False
```

Add a focused test for GET preview wiring if there is already a memo API test harness; otherwise keep this unit test and in Step 3 skip `hubspot_deal_id` rehydration when `skip_deal` is true (read `get_approval_preview` / `post_approval_preview` around the `if not deal_id and not create_new_deal: deal_id = memo hubspot_deal_id` block).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/whatsapp/test_preview_skip_deal.py -v`

Expected: FAIL (`skip_deal` unexpected kwarg)

- [ ] **Step 3: Write minimal implementation**

Add `skip_deal: bool = False` to `PreviewRequest` and to `get_approval_preview`. Before memo rehydration:

```python
if skip_deal:
    deal_id = None
    create_new_deal = False
```

Pass `skip_deal` into `resolve_preview_deal_selection`. First lines of that function:

```python
if skip_deal:
    return None, False
```

Call sites in `memos.py` must pass the new kwarg.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/whatsapp/test_preview_skip_deal.py tests/hubspot/test_preview_new_company.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/approval.py backend/app/services/preview_targets.py backend/app/api/memos.py backend/tests/whatsapp/test_preview_skip_deal.py
git commit -m "$(cat <<'EOF'
fix(preview): skip_deal clears memo deal rehydration

EOF
)"
```

---

### Task 5: NL intents for keep / skip deal / change deal

**Files:**
- Modify: `backend/app/services/conversation/intent.py`
- Test: `backend/tests/whatsapp/test_intent.py`

**Interfaces:**
- Consumes: inbound text + `state`
- Produces: `ResolvedIntent.intent` in `approve | keep | add_fields | skip_deal | change_deal | search_deal | unclear` with optional `params={"q": str}`

- [ ] **Step 1: Write the failing test**

```python
from app.services.conversation.intent import resolve_intent_by_rules

def test_keep_and_skip_and_change_deal():
    assert resolve_intent_by_rules("no actualizar", "waiting_approval", "m1").intent == "keep"
    assert resolve_intent_by_rules("quita el deal", "waiting_approval", "m1").intent == "skip_deal"
    assert resolve_intent_by_rules("sin deal", "waiting_approval", "m1").intent == "skip_deal"
    assert resolve_intent_by_rules("otro deal", "waiting_approval", "m1").intent == "change_deal"
    r = resolve_intent_by_rules("el deal de acme", "waiting_approval", "m1")
    assert r.intent == "search_deal"
    assert "acme" in (r.params or {}).get("q", "").lower()
```

Extend `ResolvedIntent.intent` comment. Keep existing approve/add/reject rules. Map `REJECT_PATTERNS` (`no`, `reject`) to `keep` when state is `waiting_approval` so reject and keep are one CRM no-op (`status=rejected`).

For `el deal de X`, a small regex is enough; do not call the LLM in the unit test.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/whatsapp/test_intent.py -v`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Add pattern sets. `search_deal` only when the text contains `deal`/`oportunidad` plus a remainder, or starts with `busca deal`. Update the LLM fallback JSON enum to the same intents so free Spanish still works when rules miss.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/whatsapp/test_intent.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/conversation/intent.py backend/tests/whatsapp/test_intent.py
git commit -m "$(cat <<'EOF'
feat(whatsapp): rule intents for keep, skip deal, search deal

EOF
)"
```

---

### Task 6: Conversation states + send card + retarget

**Files:**
- Create: `backend/migrations/034_whatsapp_retarget_states.sql`
- Modify: `backend/app/models/conversation.py`
- Modify: `backend/app/services/whatsapp/processor.py`
- Test: `backend/tests/whatsapp/test_processor_retarget.py`

**Interfaces:**
- Consumes: Task 2–5 helpers, `provider.build_preview`, `provider.find_matching_deals` / `HubSpotSearchService.search_deals_by_query`, `approve_memo_core`
- Produces: outbound split text then buttons; on `act:retarget` a list; on `pick:skip_deal` re-preview with `skip_deal=True`; on `pick:deal:{id}` re-preview with that id; on `act:keep` reject memo

States to add: `waiting_retarget`, `waiting_typed_search`. Keep `waiting_deal_choice` in the CHECK so old rows do not break; new code uses `waiting_retarget`.

- [ ] **Step 1: Write the failing test**

Mock `MessagingClient` recording `send_text` / `send_interactive_buttons` / `send_interactive_list` calls. Drive `_send_preview_for_selection` (or the new `_send_action_card` you extract) with a contact-only preview.

```python
import pytest
from app.services.whatsapp.actions import ACT_APPROVE, ACT_RETARGET, PICK_SKIP_DEAL

@pytest.mark.asyncio
async def test_action_card_splits_then_buttons(monkeypatch):
    sent = []
    class FakeWA:
        def is_configured(self): return True
        async def send_text(self, to, text, **k): sent.append(("text", text))
        async def send_interactive_buttons(self, to, body, buttons, **k):
            sent.append(("buttons", body, [b["id"] for b in buttons]))
        async def send_interactive_list(self, *a, **k):
            sent.append(("list", k))
    # call the send helper with a stub preview; assert last call is buttons with ACT_APPROVE
    # and no button body longer than 1024
```

Second test: handler for `button_id=ACT_RETARGET` sends a list containing `PICK_SKIP_DEAL`. Third: `pick:skip_deal` sets artifacts `skip_deal=True` and `selected_deal_id=None`.

Processor is large; extract `_send_action_card` and `_handle_retarget` as functions in `processor.py` (or `processor_actions.py` next to it if the file is already past ~400 new lines). Do not rewrite extraction/STT in this task.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/whatsapp/test_processor_retarget.py -v`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Migration: drop `conversations_state_check` if present and re-add including `waiting_retarget` and `waiting_typed_search`.

Replace `_send_preview_for_selection` button payload: `split_text(briefing_text)` via `send_text`, then `send_interactive_buttons(..., PRIMARY_BUTTONS)` with `button_body`. Stop passing the full preview as button body.

Default after extract: if `resolve_identity` locks a contact, preview with `skip_deal=True` (do not auto-attach a unique deal). Ambiguous contacts: list of contacts first (reuse list sender; ids `pick:contact:{id}` only if you already have contact candidates — otherwise send text “¿Quién es el contacto?” and stay on existing candidate handling). Deal is never the gate.

`waiting_approval` dispatch:

- `act:approve` / intent approve → existing `_approve_pending_memo` (pass artifacts `skip_deal`, `contact_id`, `deal_id`)
- `act:keep` / intent keep → reject memo, idle
- `act:retarget` / intent change_deal → list from `deal_list_sections` using artifacts `deal_options` or a fresh `find_matching_deals`
- `pick:skip_deal` / intent skip_deal → `_send_preview_for_selection(..., selected_deal_id=None)` with skip_deal artifact true (call `build_preview` the way GET preview will after Task 4: contact set, no deal)
- `pick:deal:{id}` → preview that deal, `skip_deal=false`
- `pick:new_deal` → `is_new_deal=True`
- `pick:type_name` or intent `search_deal` → `waiting_typed_search`; next text is `search_deals_by_query`; resend list
- field edits (`amount: 5k`) keep working as today

Do not send deal-choice as a long numbered text unless `send_interactive_list` raises; then fall back to numbered text using the same ids in a footer (`Reply *Sin deal* is not required` — use 1-based labels only in that fallback and map them from artifacts, never from `ADD_PATTERNS`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/whatsapp/test_processor_retarget.py tests/whatsapp/test_webhook_parser.py tests/whatsapp/test_copy.py tests/whatsapp/test_actions.py tests/whatsapp/test_intent.py tests/whatsapp/test_preview_skip_deal.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/034_whatsapp_retarget_states.sql backend/app/models/conversation.py backend/app/services/whatsapp/processor.py backend/tests/whatsapp/test_processor_retarget.py
git commit -m "$(cat <<'EOF'
feat(whatsapp): Meta action card and deal retarget list

EOF
)"
```

---

### Task 7: Unipile footer uses the same ids

**Files:**
- Modify: `backend/app/services/unipile/client.py`
- Test: `backend/tests/whatsapp/test_unipile_buttons_footer.py`

**Interfaces:**
- Consumes: `PRIMARY_BUTTONS` (or the same ids passed into `send_interactive_buttons`)
- Produces: one text message: body + `Responde *1* actualizar, *2* no actualizar, *3* cambiar deal`

Today the Unipile method maps `2` to “add fields” and ignores `3`. Fix that mismatch.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from app.services.whatsapp.actions import PRIMARY_BUTTONS

@pytest.mark.asyncio
async def test_unipile_footer_mentions_three_actions(monkeypatch):
    from app.services.unipile.client import UnipileClient
    sent = {}
    async def fake_send(self, to, text, **k):
        sent["text"] = text
    monkeypatch.setattr(UnipileClient, "send_text", fake_send)
    c = UnipileClient()
    await c.send_interactive_buttons("1", "body", PRIMARY_BUTTONS, chat_id="c", account_id="a")
    t = sent["text"].lower()
    assert "1" in t and "2" in t and "3" in t
    assert "add fields" not in t
```

Inbound: Unipile has no `button_id`. Processor already maps `choice == 1|2|3` in `waiting_approval`. Change that map to approve / keep / retarget (not choose-deal as 2 / edit as 3). Cover with a small unit on the map function you extract (`choice_to_action(1) == ACT_APPROVE`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/whatsapp/test_unipile_buttons_footer.py -v`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Replace the approve/add-fields footer in `UnipileClient.send_interactive_buttons`. Align processor numeric choices with `PRIMARY_BUTTONS` order.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/whatsapp/test_unipile_buttons_footer.py tests/whatsapp/test_processor_retarget.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/unipile/client.py backend/app/services/whatsapp/processor.py backend/tests/whatsapp/test_unipile_buttons_footer.py
git commit -m "$(cat <<'EOF'
fix(unipile): numbered replies match Meta approve/keep/retarget

EOF
)"
```

---

### Task 8: Wire extract path + smoke the webhook

**Files:**
- Modify: `backend/app/services/whatsapp/processor.py` (post-extract branch that currently `_find_candidate_deals` then deal-choice)
- Modify: `backend/app/api/webhooks.py` only if `MessagingClient` needs `send_interactive_list` on the protocol in processor (no route changes)

**Interfaces:**
- Consumes: memo + `resolve_identity` after extract
- Produces: `_send_action_card` with contact-first preview; deal list only after `act:retarget`

- [ ] **Step 1: Write the failing test**

Extend `test_processor_retarget.py` with `test_extract_path_does_not_send_numbered_deal_list_first`: after a stub extract, first interactive send is buttons (`ACT_APPROVE`), not a deal numbered list. If extract is too heavy to stub, unit-test the branch helper `_preview_mode_after_extract(identity) -> "contact_skip_deal" | "contact_pick" | "create_contact"` instead.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/whatsapp/test_processor_retarget.py -v`

Expected: FAIL on the new test (current code sends `_format_deal_choices`)

- [ ] **Step 3: Write minimal implementation**

Replace the block at the end of `process_whatsapp_message` that prefers `_high_confidence_match(deals)` / `_format_deal_choices`. New order: lock contact if unique; skip deal; send action card. High-confidence deal is not auto-applied.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/whatsapp/ -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/whatsapp/processor.py backend/tests/whatsapp/test_processor_retarget.py
git commit -m "$(cat <<'EOF'
feat(whatsapp): contact-first extract path, deal opt-in

EOF
)"
```

---

## Out of this plan

- signalcore-backend agent mute on Vocify phones (ops/PR there if dual replies show up)
- Meta templates / 24h Redis (Signalcore problem; Vocify replies inside an open session)
- HubSpot Lists, tickets, call outcome buttons
- Company search endpoint (use contact context)
- Pointing Meta’s callback URL off Signalcore (optional later; Vocify GET `/webhooks/whatsapp` already verifies)

## Self-review

- Spec coverage: Meta list+buttons, split, skip/reset deal, NL, contact-first, no new WhatsApp REST, Unipile fallback, preview `skip_deal` gap — each has a task.
- No TBD/placeholder steps.
- Ids `act:*` / `pick:*` are consistent from parser through Unipile footer.
