# Ask Vocify + Intelligence System — Design (v0.1)

**Status:** design for review. No code changed. **Date:** 2026-09-28. **Branch read:** `staging` @ `fd7703cd`.
**Inputs:** [proposed_plan.md](../../../proposed_plan.md), [00-contracts.md](../plans/2026-09-22-vocify-v1/00-contracts.md), [05-f07-ask-vocify.md](../plans/2026-09-22-vocify-v1/05-f07-ask-vocify.md), `product_planing.md`, the Vocify backend/frontend on `staging`, and SignalCore's Wizard (`~/signalcore/signalcore-frontend`, `~/signalcore/signalcore-backend/signalcore-backend`).
**Confidence:** static read of code and docs. I did not run tests or query staging. Where a claim depends on runtime data I say so and give the check.

---

## Implementation status (2026-09-29)

Built on `staging` (uncommitted): the Ask engine (SSE, persisted conversations, confirmations bound to the stored operation), the streaming UI, twelve read tools, IntelligenceV2 extraction, analysis of past conversations, data-backed suggestions, a chats/new/delete place, and a 77-question eval that runs against a real model.

**Model and prompt.** Ask defaults to `deepseek/deepseek-v4.1-flash` (`ASK_MODEL`), with `google/gemini-3.8-flash` as fallback. My first DeepSeek result (24/36) used the older `deepseek/deepseek-v4-flash`; 4.1 exists on OpenRouter. SignalCore's Wizard is not evidence for a tool loop: its copilot defaults to Claude Sonnet 4.6, and DeepSeek 4.1 Flash there only writes one-sentence chat titles (no tools, reasoning off). What made 4.1 work in Ask, measured on the eval: (1) reasoning is replayed between tool rounds (`reasoning_details` are captured from the stream, never stored, dropped on fallback); (2) reasoning **enabled at low effort**: as accurate as reasoning off (67/73 each), about 50% slower (median 6.1s vs 4.0s); default effort was worse (59/73) and over-explored; (3) provider pinning (`require_parameters`, `data_collection: deny`) at no accuracy cost; (4) `max_tokens` 4096, because without it OpenRouter reserves the model's 65k output window and refuses calls when the balance cannot cover that; (5) model-agnostic code fixes: reply language on the last user turn, stray-id scrub, trailing-offer trim, one retry on an empty message, and a guard for tool calls written as text (DeepSeek's DSML markup). The web prompt is its own file (`ask_prompt.md`); WhatsApp keeps its persona. The prompt uses no example people: Luis, Ana and Marta exist only in the eval's synthetic company; at runtime the prompt lists the account's real team and says only they exist.

**HubSpot: API tools on the existing client, not MCP.** `crm_call_stats` and `crm_lost_reasons` are the fast paths; `hubspot_describe` + `hubspot_query` (`crm_query.py`) answer questions no one wrote a tool for. HubSpot's Search API returns an exact `total` for any filter, so counts and per-value breakdowns cost one one-row search each. `hubspot_query` covers seven object types and validates every property and option against the portal's own schema (an unknown one comes back with the real choices, so the model corrects itself). It does: counts, group by (options counted exactly, free values tallied over up to 1,000 records and flagged when partial), sum/avg/min/max, buckets per day/week/month and per hour/weekday, `share_where` (rates: connection rate, calls over 2 minutes, win rate; per group), `compare_previous` (change vs the previous calendar month or equal window, computed in code), and top rows. Durations must carry a unit (HubSpot stores milliseconds). It refuses: sensitive properties, free-text bodies, joins across object types ("calls on deals we lost"), and any parameter combination it would otherwise ignore. Members are pinned to their own HubSpot owner id and never see teammates' names; describe calls are capped per turn. It is MCP-shaped, so a HubSpot MCP server could sit behind the same tools later. Known limits: only the four call outcomes whose GUIDs the repo confirms are labelled unless the account's disposition list is readable; a call with no outcome is unknown, never "not connected"; Pipedrive returns "unavailable".

**Token efficiency.** Fixed context per model call: ~5.1k tokens (prompt ~1.7k, tool schemas ~3.6k), down from ~6.2k; the three WhatsApp session tools are hidden on the web. What the model reads of a result is a view (`tool_view.py`): no `observed_at`, no microsecond timestamps, no null or empty row fields, no internal ids, quotes sent once, compact JSON: 33% fewer tokens across the tools (heaviest ~50%). A finished question keeps its answer, not the lookups behind it, and history is trimmed only at a question boundary (a count-based cut could orphan a tool result and make the provider reject the next turn). HubSpot aggregates cost 100-350 tokens however many records they cover; that is the reason to prefer them to record dumps.

**Rounds and errors.** Web Ask allows up to 32 tool rounds (`ASK_MAX_ROUNDS`). The last round is always a plain answer from what was found ("what you could not determine, plainly"), never a dead end. A tool error tells the model what to fix; the prompt says to retry, and to stop and say so if two lookups miss. Retried failures are not shown as red marks; only a failure that nothing followed is.

**Ask UI.** Streaming text glides instead of arriving in bursts (`useSmoothText`, pure step function tested); while working, one calm row shows the step in progress and, after the answer starts, one line opens to every step; a defaulted period is stated by the app under the answer ("Últimos 90 días."). Chats: header actions for history, new chat and, when a chat has messages, delete this chat (with confirmation); history is grouped Today / Yesterday / This week / Earlier, marks the open chat, and offers delete per row and delete all.

**Effort per question, HubSpot pacing, context.** `effort.py` routes each question before the model runs: clear wording is settled free (comparison, "why", "how should I", coaching, prioritisation, multi-part or 25+ words = high; up to 10 words with none of those = low); only the ambiguous middle goes to Jev (`classify_questions`, 1.5s timeout), and any doubt or failure means low. A turn that hits two failed lookups is bumped to high for the rest of the turn. High gets room for its reasoning (`max_tokens` 8192). Not yet measured on the eval (no credit): whether high beats low on analysis questions. HubSpot search is paced (0.25s apart) and a 429 is retried, because HubSpot's per-second search limit answers without `retryAfter`, which the client does not retry; failures are reported as what they are (`hubspot_busy`, `hubspot_unreachable`, `hubspot_reconnect`, `hubspot_rejected`), and "CRM unavailable" is reserved for "not connected". The model sees the last 24 messages (12 question-and-answer pairs) after a question boundary; a reload restores the same window; older turns stay in history but not in context, and old lookups are never replayed.

**Objections and obstacles are separate at the source.** `intelligence_v2` extracts `kind: objection | obstacle` with their own categories, the rep's reply as a validated quote, who said it (read from the transcript), meeting agreement and competitors. Old v1 blocks read as objections and are stale, so "analyse the rest" re-reads them. Hoy no longer turns an open obstacle into an `objection_open` signal.

**When analysis happens.** New conversations: at extraction, if `INTELLIGENCE_EXTRACT_ENABLED` is on (it defaults to off; whether staging/prod set it is not visible from the repo). Past conversations: an owner/admin clicks "Analizar el resto" in the coverage note (or `POST /api/v1/intelligence/backfill`); it reads only what is missing or stale, three at a time, one run per company.

**Eval** (`backend/evals/ask/`, `python -m evals.ask.run [--model ID]`; reports in `reports/`): 77 questions: 36 original, 20 general HubSpot, 7 shares/comparisons/time of day, 10 held-out written after the tools (nothing tuned to them; all passed first time), 4 follow-ups. On the final code (with effort routing, HubSpot pacing and the DSML guard), DeepSeek V4.1 Flash scores 74/77, median 5.2s: the three misses are tool-count only (no wrong number, leak, language slip or refusal). Gemini 3.8 Flash scores 74/77 (median 6.4s); its misses include one wrong-format fallback line and tool-count. Runs vary by about 2-3 cases. The effort router itself is not compared against a fixed effort on the eval. Earlier runs in this section hit OpenRouter 402 (credit) and are superseded.

**Departures from this spec, on purpose:** no migration 050 (the turn body carries everything); Stop ends the reader, not the run; no partial-answer persistence (recovery polls the persisted turn); the number lint accepts integers up to 10 and understands thousand separators and `k`; DeepSeek is the default here, before D3 (data handling) was answered, mitigated by provider pinning, which is not a DPA.

**Not built:** thumbs up/down, "Ask about this" entry points, context chip, weekly readout, per-rep objection *response* comparison, joins across HubSpot object types, Pipedrive tools.

**Bugs found while building, fixed with tests:** the loop replaced an empty session dict; confirm reported success before the write ran; a confirmed write reloaded as pending; no retry on a 429/5xx before the first byte; a failed playbook read was reported as "not published"; filters silently ignored (an `end_date` with no start, a bucket with no group); a bare duration filter in the wrong unit returned every connected call; history trimmed between a tool call and its result; an empty final message shown as "Done."

---

## 0. Verdict in one screen

1. **The data substrate is good. The intelligence surface barely exists.** V1 built typed facts (C04), scores/adherence (C14), patterns (C13), Hoy signals, briefs, reports and team aggregation. Ask Vocify cannot read any of it: `OPENAI_TOOLS` is HubSpot lookups and writes only ([tools.py:40](../../../backend/app/services/crm_copilot/tools.py)). `get_team_metrics` exists in the dispatcher ([tools.py:530](../../../backend/app/services/crm_copilot/tools.py)) but is not in the tool list, and the tool context has no role or company, so it could never pass its own permission check.
2. **Don't build "intelligence" as a module. Build one spine and let every surface render it.** `Interaction → evidence-backed facts → deterministic metrics → surfaces`. Today, briefs, score, reports, team dashboard, live assist and Ask are renderers of the same facts. Ask is the *query layer* of that spine, not a second agent.
3. **The LLM narrates; it never computes.** Numbers come from a metric registry. Every claim carries an evidence id the server validated. Coverage wording is generated by code, not by the model. That is what stops "AI slop", and it is what lets a cheap model (DeepSeek V4 Flash) be safe.
4. **The head-of-sales questions you listed need extraction that does not exist yet.** "What objection, at what moment, how did they reply, did it work" needs an *objection episode* (raise + rep response + outcome + position in the call). Today an objection is `category + resolution + quote`. C04 already reserves `response` and `start_ms`; nothing fills them.
5. **Ask has correctness gaps that must be fixed before adding intelligence** (§2.2 G2–G4): confirmations are not bound to a persisted operation and can report success without a write, working memory lives in process RAM, and the question is overwritten by the answer in the turn table.
6. **SignalCore's Wizard is the right UX pattern, with fixes.** Copy its typed SSE stream, interleaved text/tool steps, choice cards, confirm gate, entity-bound tool args, history rail and precomputed greeting. Fix its 9–11px type, hover-only copy, English-only warning cards, raw JSON in confirmations, and per-bubble shadows (§2.3, §7).
7. **DeepSeek V4 Flash is a fair default only behind an eval gate and a data-handling decision.** Your own playbook says it is "cheap but QA can be noisy" and must run without a reasoning parameter; `loop.py:225` hardcodes one. Your own compliance profile says OpenRouter is "non-regulated workloads only" ([compliance.py](../../../backend/app/services/llm/compliance.py)) while the tools will return transcript quotes (§6.5).

**Decisions I need from you** are in §11. Everything else has a recommendation.

---

## 1. What I reviewed

| Area | Where | Notes |
|---|---|---|
| Plan and contracts | `proposed_plan.md`, `00-contracts.md`, F07/F09/F10/F15 plans | The plan is Spanish, sequential, contract-first. Its F07 row carries your note "PERMITELO. TIENES QUE SIMULAR signalcore-backend Wizard." |
| Project UI rules | `.cursor/rules/no-extra-ui.mdc`, `.cursor/skills/vocify-ux-coherence/SKILL.md` | Proportional UI, reuse existing patterns, Granola as the fluidity bar, "sin AI slop" as acceptance criteria. §7 follows them. |
| Vocify Ask (backend) | `api/ask.py`, `services/crm_copilot/{loop,tools,web_sessions,prompts,route}.py`, `soul.md`, `skills/*.md` | Loop shared with WhatsApp. Non-streaming. HubSpot-shaped tools. |
| Vocify Ask (frontend) | `src/features/ask/components/{AskPanel,VoiceComposer}.tsx`, `DashboardLayout.tsx:287` | 375-line panel, plain-text lines, poll every 2 s. |
| Intelligence pipeline | `services/intelligence/{extract,interpret,patterns,worker,annotations}.py`, `prompts/intelligence_v1.md`, `models/intelligence.py` | Two producers of the same JSON key (§2.2 G6). |
| Coaching / team / Today | `services/coaching/*`, `services/team_insights/*`, `services/hoy/*`, `services/reporting/*`, migrations 037–049 | Solid, deterministic, tested. |
| SignalCore Wizard | `components/features/wizard/*`, `lib/hooks/use-ask-ai-chat.ts`, `lib/ask-ai/*`, `lib/copilot/*`, `docs/ask-ai/*`, backend `api_gateway/app/services/copilot/*`, `service-orchestrator/.../wizard_greeting/*` | ~7.7k frontend lines, ~6.5k backend lines of copilot. |

Not reviewed: desktop/extension internals beyond what the plan cites; live data.

---

## 2. Honest assessment

### 2.1 What is strong (keep)

- **Contract discipline.** `input_revision`, `null ≠ false`, coverage envelopes, evidence quotes validated against the source. This is rarer than it sounds and it is exactly what a trustworthy assistant needs.
- **Deterministic core.** `compute_adherence`, `aggregate_adherence` (sums counts, never averages rates), `objection_counts`, `signals_for_contact`, `rank_cards`, `authorized_scope` ("free text never widens the scope"). These become the registry's first metrics unchanged.
- **Scope rules already exist** (`activity_scope.py`, `TeamAccessError`). Ask only has to call them.
- **Product stance is right for a head of sales:** adherence as met/applicable, meeting booked ≠ close, no tone/emotion detection, no leaderboards, reps sorted alphabetically (`sort_reps_by_name`).

### 2.2 Gaps between plan/code and what you asked for

| # | Finding | Evidence | Why it matters |
|---|---|---|---|
| G1 | **Ask has zero intelligence tools.** It cannot read facts, scores, patterns, signals, reports or outcomes. | `OPENAI_TOOLS` ([tools.py:40](../../../backend/app/services/crm_copilot/tools.py)); dead `get_team_metrics` branch at :530; `CopilotContext` has no `role`/`company_id` ([tools.py:163](../../../backend/app/services/crm_copilot/tools.py)) | Ask cannot answer any question that motivates V1 (objections, adherence, "what happened with this deal"). |
| G2 | **A confirmation can report success without a write.** `confirm_operation` returns `applied: true / succeeded` before anything runs ([web_sessions.py:201](../../../backend/app/services/crm_copilot/web_sessions.py)); then `_loop("", confirm=True)` runs against per-user RAM ([ask.py:287](../../../backend/app/api/ask.py)); the write result is never checked, and `applied` is persisted at [ask.py:303](../../../backend/app/api/ask.py). After a restart the pending tool is gone and the UI still says done. | Violates the plan's own DoD "ninguna escritura sin confirmación válida" and C07 ("confirmación valida operación/target/revisión"). The stored confirmation holds `operation_id, revision, contact_id` but not the tool or arguments. |
| G3 | **Working memory is process RAM, keyed by user, not conversation.** | `_sessions: dict[str, dict]` ([web_sessions.py:205](../../../backend/app/services/crm_copilot/web_sessions.py)) | Lost on deploy, wrong on scale-out, two conversations share one memory, no history is possible. |
| G4 | **The turn table is lossy.** One `body` column holds the question, then is overwritten by the answer JSON on completion. No conversation list, no title. Actor is a module-global dict. | `persist_turn` ([web_sessions.py:~100](../../../backend/app/services/crm_copilot/web_sessions.py)); `_actor` ([:204](../../../backend/app/services/crm_copilot/web_sessions.py)) read lazily at [tools.py:~545](../../../backend/app/services/crm_copilot/tools.py) | A reload loses the question. A history rail is impossible. `_actor` is not a confirmed leak today (`live_ask_loop` reads `user_id` before its first await) but any tool that reads it after an await can see another request's actor. |
| G5 | **Extraction is thinner than C04 and thinner than your questions.** (a) Objections have no rep response, no timing, no outcome beyond `resolution`. (b) Commitments without a due date are **dropped** ([extract.py:78](../../../backend/app/services/intelligence/extract.py)) although C04 says `due_at` is nullable. (c) `competitor_mentions: []` and `playbook_observations: []` are hardcoded ([extract.py:101](../../../backend/app/services/intelligence/extract.py)) though `MemoExtraction.competitors` already exists. (d) `pain_confirmed` is a boolean; *which* pain is only in legacy `painPoints`. | `prompts/intelligence_v1.md`; `shape_intelligence` | The "what happened with this deal" answer and the objection→response→outcome analysis cannot be evidence-backed. |
| G6 | **Two writers replace the same key.** `extract.py` writes `extraction.intelligence` (interest, objections, commitments; `meeting.agreed = null`). The Jev worker's `store()` then calls `extraction_with_intelligence`, which *replaces* `extraction["intelligence"]` with a block holding only `pain_confirmed`, `meeting`, `evidence` ([worker.py:135](../../../backend/app/services/intelligence/worker.py), [interpret.py:12](../../../backend/app/services/intelligence/interpret.py)). The reuse check reads `memo.get("intelligence")`, a top-level column that no migration 037–049 creates, so it never reuses. | Static read. **Verify on staging** with the SQL in §10. | If both run, Hoy loses objections/commitments or team metrics lose `meeting.agreed`, depending on order. |
| G7 | **The whole typed layer is off by default.** `INTELLIGENCE_EXTRACT_ENABLED = False`, `INTELLIGENCE_WORKER_PUBLISH = False` ([config.py:201-203](../../../backend/app/config.py)). | Cannot tell from the repo whether staging/prod set them. | Ask intelligence tools would return `unavailable` everywhere. Check the env first. |
| G8 | **Plan forbids streaming; you overrode it.** F07 says "no streaming simulado", poll every 1–5 s. The OpenRouter provider has no streaming path (`chat`, `chat_tools`, `chat_json` only). | [05-f07 §A9](../plans/2026-09-22-vocify-v1/05-f07-ask-vocify.md); `providers/openrouter.py` | Real SSE is not "simulated". Keep the persisted turn as the recovery path so the plan's idempotency guarantees survive. |
| G9 | **Model settings are shared and hardcoded.** One `CRM_COPILOT_MODEL` serves WhatsApp and web; `extra={"reasoning": {"effort": "low"}}` is hardcoded ([loop.py:225](../../../backend/app/services/crm_copilot/loop.py)). | `config.py:64` | Swapping to DeepSeek by id alone sends a parameter your own playbook says to omit. |
| G10 | **The Ask UI is a stub relative to A9.** Plain-text lines, no markdown, no tool progress, no evidence, icon-only confirm (check / x), one `sessionStorage` conversation, `ConversationThread`/`TurnStatus`/`useAskConversation` not created. | `AskPanel.tsx` | This is the part you called "super, super, super important". |

### 2.3 SignalCore Wizard — what to copy and what to fix

**Copy (adapt names, keep the idea):**

| Wizard piece | Where | Vocify adaptation |
|---|---|---|
| Typed SSE vocabulary: `session, phase/state, content, tool_start, tool_result, confirm_required, action_prompt, action_card, blocker, error` | `lib/ask-ai/types.ts`, `agent_loop.py` | §6.6. Add `evidence`, `blocks`. |
| Product-state labels, not raw phases (`understanding/planning/building/debugging/verifying/answering`) | `phases.py` | `understanding / reading / analyzing / drafting / checking`. |
| Interleaved text and tool steps in SSE order (`AssistantStreamBlock`) | `use-ask-ai-chat.ts` | Same. Collapse to one summary line when done (§7). |
| Entity-bound tool args: model-invented ids are overridden by the on-screen entity | `context_guard.py` | Bind `contact_id/deal_id/memo_id` to the page or `@mention`. Reject invented ids. |
| `frontend_context` snapshot, sanitized, ≤20 KB, rebuilt per message, ignored on confirm | `frontend_context.py` | Send `{surface, route, contact_id?, deal_id?, memo_id?, period?}`. Never transcripts. |
| Confirm gate + `offer_user_choices` (clarify with buttons) | `confirmation_gate.py` | Already in Vocify's loop; keep, but persist (G2). |
| Loop safety: self-correction, circuit break → `blocker`, tool-result redaction, round cap, per-question reasoning policy | `self_correction.py`, `tool_result_redact.py`, `reasoning_policy.py` | Reuse the ideas; add the numeric lint (§6.3). |
| History rail (Today/Yesterday/Week/Older), rename, delete, one-sentence titles | `wizard-history-rail.tsx` | Same buckets. |
| Composer: auto-grow, send↔stop swap, Enter/Shift+Enter, focus glow | `wizard-composer.tsx` | Same behaviour, Vocify tokens. |
| Home suggestions derived from real state, not static chips | `home-suggestions.ts` | Role- and data-aware (§7.2). |
| Proactive greeting precompute with a signal fingerprint, min 8 h / max 24 h regeneration, concurrency cap | `wizard_greeting_service.py` | §6.7, but deterministic-first. |
| Tool-result effects → invalidate queries + "data refreshed" notice | `tool-result-effects.ts` | After a confirmed write, refresh Today/contact queries. |
| One panel core, two hosts (drawer, full page) | `wizard-panel.tsx`, `/wizard` | `AskThread` core; drawer and `/dashboard/ask` hosts. |
| Chat survives navigation; resizable drawer; Esc closes; new-chat reset dialog | `wizard-drawer.tsx` | Same. |

**Fix (Wizard gets these wrong, Vocify's plan already forbids them):**

| Wizard issue | Where | Fix |
|---|---|---|
| Type at 9–11 px (`text-[9px]`, `text-[10px]`, `text-[11px]` on cards, chips, suggestions) | `wizard-panel.tsx`, `wizard-home.tsx` | Floor 12 px for metadata, 15 px body (Vocify's existing body size). |
| Copy button `opacity-0` until hover | `wizard-panel.tsx` | Always visible at low emphasis; full on hover/focus. Works on touch. |
| "Blocker Detected", "Error", "Action required" hardcoded English | `wizard-panel.tsx` | `t.product.*`, ES and EN. |
| Confirm card prints `JSON.stringify(args)` | `wizard-panel.tsx` | Plain-language action + field diff. Plan A9: "sin mostrar llamadas a herramientas ni IDs internos". |
| Server confirmation text leaks the tool name: "Copilot needs your confirmation before it runs `tool`" | `agent_loop.py` `_confirmation_summary` | Build the sentence from the operation (§6.6). |
| Bubble tails and `shadow-md` on every message; mascot avatar | `spark-speech-bubble.tsx` | Vocify: content sits on paper; shadow only on floating chrome (`THEME_TOKENS`). No mascot. |
| Confirmations in Redis with a 10 min TTL | `confirmation_gate.py` | Vocify already stores turns in Postgres. Persist the operation payload instead (G2). |
| No notion of evidence or citation | — | Vocify's differentiator. §6.3, §7. |

---

## 3. The system: one spine, four buckets

```
CAPTURE                 FACTS (per interaction)           METRICS (deterministic)        SURFACES
desktop / extension  →  IntelligenceV2 (evidence-backed) →  metric registry (§5)      →  Today (F05/F06)
calls / WhatsApp        interest · pains · objection        pure functions, versioned,     Pre-brief (F03) · Post-brief (F11)
notes (F10)             episodes · commitments ·            role-scoped, min-sample        Score (F09) · Live assist (F12)
                        competitors · stakeholders ·        gated, coverage-aware          Reports (F13) · Team (F15)
                        meeting agreement                                                  ASK VOCIFY (F07) ← query layer
```

**Bucket → feature map** (your four buckets over the 15 features):

| Bucket | Features | Role in the spine |
|---|---|---|
| Capture | F01 desktop, extension, calls, WhatsApp, F10 notes | Produce interactions and human notes. |
| Automate | F02 follow-up, F14 meeting write, CRM field updates, F05/F06 tasks | Consume facts, propose an action, wait for approval. |
| Assist | F03 pre-brief, F04/F05 prioritization/Today, F12 live checklist, F11 post-brief | Read facts about *this* contact/call, act in the moment. |
| Educate | F08 playbooks, F09 score, F10 objections, F13 reports, F15 team, **Ask** | Read facts about *many* interactions, explain, teach. |

**Rule that keeps this coherent:** a fact is extracted once (C04), a metric is defined once (registry), and every surface calls the same function. The plan already states this for team reads ("dashboard, chat y reporte consultan la misma agregación", C19). This design generalises it to all surfaces and gives it one home.

**How the features interconnect through Ask** (all deterministic links, no new agent):

| From an answer | Action card | Backing feature |
|---|---|---|
| "Marina asked for the case study" | Draft follow-up | F02 |
| "3 promises are due today" | Open in Today | F05/F06 |
| "You skipped *decision maker*" | Open call at 12:41 | F01 playback / F11 |
| "Price objection is open at Acme" | Show playbook answer | F08 |
| "Meeting agreed Tue 10:00" | Review meeting | F14 |
| "Adherence fell to 58%" | Open team view, filtered | F15 |
| A resolved objection with a strong reply | Promote to playbook example (manager) | F08, closes the "patrones que funcionan" open item |

---

## 4. Layer 1 — Fact ledger: IntelligenceV2

Keep C04's rules (one production per `input_revision`, quotes must exist in the source, unknown ≠ false). Change what is extracted, and stop the two-writer problem.

### 4.1 One producer, merged write

- `extract.py` (LLM, open text: objection episodes, commitments, pains, competitors, stakeholders) and the Jev classifier (closed vocabulary: `meeting_agreed`, `pain_confirmed`, `objection_kind`, `outcome`) both contribute to **one** `IntelligenceV2` object. The worker merges by field ownership and never replaces the block. Field ownership table lives next to the model.
- Keep the plan's hybrid decision: closed-vocabulary fields (category, kind, outcome, agreement) come from the classifier; the LLM finds the quotes; the server validates every quote is a substring of the source (already implemented in `_evidence`).
- Add the missing `memos.intelligence` reuse check against `extraction.intelligence` (or drop the dead top-level read).

### 4.2 Objection episode (the head-of-sales unit)

```json
{
  "id": "obj-…",
  "category": "price|timing|authority|competitor|status_quo|trust|other",
  "kind": "objection|obstacle|unknown",
  "raised":   { "quote": "…", "turn_id": "…", "t_ms": 412000, "position": "early|middle|late" },
  "response": { "quote": "…", "turn_id": "…", "t_ms": 421000, "matched_entry_id": null },
  "outcome": "resolved|open|deflected|unknown",
  "evidence_refs": ["ev-…"]
}
```

- `response` and `t_ms` already exist in C04/C13 (`response nullable`, `start_ms`). This fills them.
- `position` is **deterministic** (`t_ms / duration` in thirds). No invented "call phase". When a playbook step is observed at that time, F12/F09 can add the step id later.
- `matched_entry_id` is set only by server-side matching against the published playbook entry for that category. The model does not decide it.
- `outcome = deflected` (rep changed subject, prospect did not accept) is the distinction that separates a *handled* objection from a *survived* one. Keep `unknown` when the transcript does not show it.

### 4.3 Other facts

| Fact | Shape | Replaces |
|---|---|---|
| `pain_points[]` | `{text, quote, evidence_ref}` | Boolean-only `pain_confirmed`; legacy `painPoints` strings |
| `competitor_mentions[]` | `{name, claim, quote, evidence_ref}` | Hardcoded `[]` |
| `stakeholders[]` | `{role, name?, decision_maker: true\|false\|null, evidence_ref}` | Nothing (enables "single-threaded" risk) |
| `commitments[]` | `due_at` nullable, `temporal_precision: none\|date\|time` | Silent drop of commitments without a date (fix [extract.py:78](../../../backend/app/services/intelligence/extract.py)) |
| `next_step` | `{text, owner: rep\|prospect, due_at?, quote}` | Free text in `nextSteps` |

Hoy's adapter ([materialize.py:_commitments](../../../backend/app/services/hoy/materialize.py)) keeps requiring `due_at` for `commitment_due`; a dateless commitment instead feeds a new `open_loop` metric so it is visible without inventing a date.

### 4.4 Rollout of extraction

Bump `prompt_version` to `intelligence_v2`. Old memos stay valid as v1; every Ask answer reports coverage as "n of m interactions analysed" so a partial backfill is honest, not hidden. Backfill uses the existing `memo_jobs` claim/lease path, newest first, capped per run. Migration `050` is additive columns on `interaction_patterns` (`raised_t_ms, response_t_ms, position, outcome`), no new table.

---

## 5. Layer 2 — Metric registry (what a head of sales actually needs)

A metric is a pure function `(rows, period, scope) → {value, n, coverage, definition_id}` with a fixed definition string, a minimum sample, and a plain-language "what it does not mean". Ask, dashboard, reports and Today call the same function.

**Design rule for "minimal input, better data":** the head of sales configures three things at most — publish a playbook (exists), optionally define what a good call is (plan §4.4 idea), optionally map the "meeting booked" stage (plan §6). Everything below is derived with zero configuration.

Readiness: **Now** = data and service exist. **v2** = needs IntelligenceV2 (§4). **Later** = needs data we do not yet capture reliably.

### 5.1 Activity → outcome funnel

| Metric | Definition | Question it answers | Ready |
|---|---|---|---|
| `connect_rate` | connected / attempts (from `screening_outcome`) | Are reps reaching people? | Now (`activity_counts`) |
| `meeting_rate` | meetings agreed / connected. **Never merged with close.** | Is the cold-call motion converting? | Now (`intelligence.meeting.agreed` via Jev) |
| `meeting_to_won` | won / (won + lost), known outcomes only; open and unknown shown apart | Do meetings become revenue? | Now (`adherence_crm_outcomes`), coverage-gated |
| `time_to_first_ask` | offset of the first meeting ask / call length | Do reps ask for the meeting early enough? | v2 |

### 5.2 Process (playbook)

| Metric | Definition | Question | Ready |
|---|---|---|---|
| `adherence` | met / applicable, with `coverage` and unknowns shown | Is the team following the method? | Now (`aggregate_adherence`) |
| `step_miss` | per-step `missed` count over applicable | Which step do we skip most? | Now from `playbook_observations` |
| `adherence_trend` | weekly adherence, per rep, min n | Is coaching working? | Now |

### 5.3 Objections (the Educate core, your exact ask)

| Metric | Definition | Question | Ready |
|---|---|---|---|
| `objection_mix` | share by category, `objection` kind only (obstacles excluded) | What do we hear most? | Now (`objection_counts`) |
| `objection_resolution` | resolved / (resolved + open + deflected), unknown apart, per category and per rep | Which objections do we lose on, and who handles them? | v2 (`outcome`) |
| `objection_timing` | distribution by `position` | When in the call do they appear? | v2 |
| `objection_to_meeting` | P(meeting agreed) among calls with an objection of category X, split by resolved vs open. **Association, never causation.** | Does handling price well move meetings? | v2, min n |
| `response_examples` | resolved episodes' rep `response` quotes by category (retrieval, not a number) | How did people actually answer it? | v2 |

### 5.4 Follow-through (unique to Vocify — commitments have dates and Today has status)

| Metric | Definition | Question | Ready |
|---|---|---|---|
| `commitments_on_time` | commitments whose Today signal reached `done` by `due_at` / commitments due. Proxy: Today completion, not verified CRM activity. State the proxy in the answer. | Do reps do what they promise? | Now |
| `open_loops` | pending commitments + open objections with no future task/meeting | What is about to fall through? | v2 for dateless commitments, Now otherwise |
| `going_cold` | warm interest, ≥10 days without a touch (`COLD_AFTER`) | Which warm contacts are we losing? | Now (`signals_for_contact`) |
| `follow_up_speed` | median hours from call end to follow-up handoff (F02 `sent` = handoff) | How fast do we follow up? | Check F02 timestamps |

### 5.5 Deal health (per deal, deterministic)

| Metric | Definition | Question | Ready |
|---|---|---|---|
| `interest_trend` | `interest` across touches (high→medium→low) | Is this deal warming or fading? | Now |
| `single_threaded` | one stakeholder across all touches; `decision_maker_seen` true/false/unknown | Are we talking to the buyer? | v2 |
| `competitor_exposure` | deals with a competitor mention and no matching playbook entry | Where do we lack a battle card? | v2 |
| `stale_next_step` | no future task or meeting on an interested deal | Which deals have no next step? | Now (CRM read, coverage-gated) |

### 5.6 Voice of customer

| Metric | Definition | Question | Ready |
|---|---|---|---|
| `pain_top` | pains mentioned by ≥2 distinct prospects, grouped, with quotes. Grouping is model-assisted and labelled so. | What do prospects complain about? | v2 |
| `loss_reasons` | CRM `lost_reason` + the last open objection on lost deals | Why do we lose? | Now for CRM reason, v2 for objection |

### 5.7 Later (do not promise)

`talk_ratio`, `questions_per_10min`, `longest_monologue`: deterministic but need reliable speaker roles (`capture_turns.speaker_role`). Ship only when coverage per call is reported honestly. Tone or sentiment: out of scope by decision.

### 5.8 What the answer never does

- No causal claims ("adherence caused wins"). The registry tags each metric `descriptive` or `association`; the prompt and the lint enforce it.
- No conclusion below the minimum sample. Existing code gates at n < 5 (`sample_limited`); Ask says "too few to conclude" in words the server writes.
- No ranking by default (plan bans leaderboards). "Who is slipping?" is answered as "needs attention on step X" with n and a fixed alphabetical order, only for owner/admin, only when asked. See decision D1.

---

## 6. Layer 3 — The Ask engine

### 6.1 Actor and scope

Replace `_actor`/`_sessions` with an immutable per-request actor built from `Membership`:

```python
@dataclass(frozen=True)
class AskActor:
    user_id: str; company_id: str; role: str      # owner|admin|member
    timezone: str; locale: str                    # es|en
```

Passed via `CopilotContext.actor`. Every tool receives it and applies `visible_user_ids(actor)` (from `activity_scope.py`). Members get themselves; owner/admin may pass `scope`, validated by `authorized_scope`. The role is the server's; free text never widens it. Tools a member cannot use are **not sent to the model** at all.

### 6.2 Tool catalogue

Keep the existing CRM tools. Add read-only intelligence tools. Every result is an envelope, never raw rows:

```json
{ "coverage": "complete|partial|forbidden|unavailable", "observed_at": "…",
  "period": {"start":"…","end":"…","tz":"Europe/Madrid"}, "n": 14, "n_analysed": 6,
  "items": [ … ], "evidence": [ {"id":"ev-…","memo_id":"…","quote":"…","speaker":"prospect","t_ms":412000,"at":"…","rep":"…"} ],
  "metric_id": "objection_resolution@1", "reason": null }
```

| Tool | Backed by | Roles | Answers |
|---|---|---|---|
| `deal_story(contact_id\|deal_id)` | memos + intelligence + CRM provider + `hoy.signals` | all (own) | "What happened with Marina?" Chronological touches, open loops, risk flags, next best action |
| `find_interactions(filters)` | memos + patterns | all (own) / admin (team) | "Show me calls where price wasn't resolved" |
| `interaction_detail(memo_id)` | memo + brief + score | own / admin | One call, with playable timestamps |
| `my_today()` | `hoy` TodayView | all | "What do I do today?" |
| `prep_call(contact_id)` | F03 brief + open objection + playbook entry | all | "Prep me for 3pm with Acme" |
| `explain_score(memo_id)` | `memo_scores` + observations | own / admin | "Why did this call score low?" |
| `playbook_lookup(motion, topic)` | published playbook | all | "How do we answer *too expensive*?" |
| `metric(id, period, motion?, user?)` | registry | own / admin | Any §5 metric |
| `objection_breakdown(period, motion?, user?)` | patterns | own / admin | Mix, resolution, timing |
| `response_examples(category, limit)` | resolved episodes | own / admin (see D2) | "How did our best answer price?" |
| `team_roster()` | company members | admin | Resolves names to ids so the model never invents one |
| `outcomes(period)` | `team_outcome_observations` | admin | Won/lost with coverage |

Writes (unchanged rules, new persistence — §6.6): `create_note`, `create_task`, `apply_write`, `draft_followup` (F02, draft only), `snooze_signal` (F06). About 20 tools total, short disjoint descriptions, role-filtered per request.

### 6.3 Grounding contract (the anti-slop core)

The model writes short markdown. The server then runs four checks before the turn completes:

1. **Evidence tokens.** Claims taken from a tool end with `[ev-…]`. The server keeps only tokens that appeared in a tool result *this turn* and attaches the evidence payload (quote, speaker, time, rep, memo). Unknown tokens are stripped and the sentence is flagged.
2. **Numeric lint.** Every number, percent and date in the answer must appear in a tool result of the turn. On failure, re-ask once ("rewrite using only the returned numbers"); on a second failure, show the deterministic table fallback instead of the prose.
3. **Coverage note is generated by code**, not the model: the minimum coverage across the turn's tool envelopes, rendered from a template ("Based on 6 of 14 conversations; 8 not analysed yet"). `partial`, `forbidden` and `unavailable` have distinct, fixed wording, so a failed read is never phrased as "no activity".
4. **Language lint.** No causal verbs on `association` metrics; no tone/emotion claims; no tool names, ids or file paths in text.

Answer shape (enforced by prompt, template and lint): **headline sentence → at most 3 supporting facts → one recommended action**. Example for your "what happened with this deal":

> **Marina López (Acme):** interested, but on Tue she said it's not a good moment. **Pain:** manual follow-up takes ~3 h/week [ev-3f9a]. **Open:** price objection, unanswered [ev-71c2]. **Suggested:** call back after the 15th. [Open in Today] [Draft follow-up]
> *Based on 3 conversations and CRM notes. Emails not read (scope missing).*

### 6.4 Routing and skills

Reuse the existing skills mechanism (`skills/*.md`, `load_skill`) but **pre-route deterministically** so a small model does not have to choose: `route.py` gains a rule-based router that uses the UI context (page entity) and keywords to preload one skill. Add skills: `deal_review`, `call_prep`, `rep_review`, `objection_review`, `pipeline_risk`, `weekly_readout`. Each skill states tool order, answer shape and forbidden claims. Confirmations and `offer_user_choices` stay in the loop.

### 6.5 Model plan (DeepSeek V4.1 Flash)

- Config: `ASK_MODEL` (default `deepseek/deepseek-v4.1-flash`) and `ASK_FALLBACK_MODEL` (default `google/gemini-3.8-flash`); WhatsApp keeps `CRM_COPILOT_MODEL`. Per-model request parameters are data in `model_profile.request_extra`, not literals in the loop.
- DeepSeek V4.1 Flash reasons by default and OpenRouter returns `reasoning_details`; they must be replayed between tool rounds. It runs at low effort, pinned to hosts that support tools and reasoning and do not keep prompts, with `max_tokens` 4096. See the implementation status for the measurements behind each choice.
- **Eval gate before any model change:** `python -m evals.ask.run --model <id>` (77 questions, real model, fixture data). Critical cases must pass 100%: member asking for team data, write without confirmation, invented number, invented id, a question no data can answer.
- Fallback on any failure of the first call to `ASK_FALLBACK_MODEL`, logged, so a provider outage is visible.
- **Data handling (still needs your call, D3):** OpenRouter is marked "non-regulated workloads only" (`gdpr_dpa: false`) and `deal_story` / `find_interactions` return transcript quotes about named prospects. Provider pinning (`data_collection: deny`) narrows who can receive them; it is not a DPA. The stricter options remain: keep quote-bearing turns on `vertex_ai` (Madrid, DPA, already supported via `LLM_PROVIDER`) or send DeepSeek only aggregate, quote-free tool results.

### 6.6 Streaming, persistence, recovery, confirmations

Real SSE, not simulated tokens. The persisted turn stays the source of truth.

```
POST /api/v1/ask/conversations/{cid}/turns/stream        Accept: text/event-stream
  body: { client_turn_id, text, context?: {surface, contact_id?, deal_id?, memo_id?, period?} }

turn        {turn_id, replayed}
state       {state: understanding|reading|analyzing|drafting|checking, label}
tool_start  {call_id, tool, label}                        # label from i18n key
tool_result {call_id, ok, summary, coverage, n}           # never the raw payload
content     {delta}
evidence    {items:[…]}
blocks      {coverage_note, actions:[…], followups:[…]}
choices     {prompt, options:[{id,label,detail}]}
confirm     {operation_id, revision, target, summary, changes:[{field,from,to}]}
blocker     {code, message, action}
error       {code, message, retryable}
done        {turn_id, status}
```

- **Idempotency** keeps the existing `save_ask_turn` key `(user, conversation, client_turn_id)`. A replay returns the stored turn.
- **Recovery:** the server finishes the loop even if the client disconnects and writes `partial_answer` about once a second. A dropped stream falls back to the existing `GET …/turns/{turn_id}` poll (1 s → 3 s → 5 s per A9). "Cerrar y reabrir recupera el mismo turno" still holds.
- **Cancel:** `POST …/turns/{id}/cancel` stops between rounds. It never cancels an already-confirmed write.
- **Confirmations (fixes G2):** the `confirm` event is backed by a row in `copilot_operations` holding tool, arguments, target, revision, status. `POST …/operations/{id}/confirm` executes *that stored payload*, records `succeeded | failed | uncertain`, and returns the real result. `uncertain` reconciles before any retry (C07). The UI never shows success before the write result.
- **Persistence (fixes G3, G4):** migration `050` adds `ask_conversations` (id, company_id, user_id, title, `memory jsonb`, timestamps) and splits `copilot_web_turns.body` into `question` and `answer` columns. Title = first question, truncated, with an optional cheap one-line summary later.
- **Transport:** `X-Accel-Buffering: no`, a comment heartbeat every 15 s, request-scoped actor. WhatsApp stays non-streaming on the same loop.

### 6.7 Proactive layer (no new tables, no LLM required)

- **Ask home** shows up to three insight cards computed on read from the registry, cached about 5 minutes per actor.
  - Rep: top Today card; overdue commitments; the step skipped on the last call.
  - Manager: the largest week-over-week change with n ≥ 5 among `connect_rate, meeting_rate, adherence, top objection share`; reps with overdue commitments; objections open across k deals.
- Each card ends in **Ask about this**, which seeds a prompt with context.
- **Weekly readout** (F13 email + bell, Ask home): the same three findings, ≤ 120 words, with evidence links. Deterministic detection, templated wording; the LLM only rephrases if enabled. This is the Wizard's precomputed-greeting idea (fingerprint, regenerate on change) without its LLM cost.

### 6.8 One engine, many renderers

The answer is structured blocks (`headline, facts[], evidence[], coverage_note, actions[], followups[]`). Web renders it rich. WhatsApp renders `headline + 3 lines + link`, no evidence UI. F13 reuses `reporting/presentation.py`. Desktop/extension can render the same blocks through `shared/ui` later.

---

## 7. Ask UX/UI specification

This section is the *proposal* the project rules ask for before UI is built (`no-extra-ui.mdc`: propose first when a flow or screen changes). The fluidity bar is Granola: smooth, quiet, frictionless. §7.7 declares every new element's place, weight and reason.

### 7.1 Principles

1. **Answer first.** Headline, then evidence, then detail on demand. Matches the plan's "mostrar primero el motivo o la acción útil".
2. **Show the work, quietly.** A one-line activity summary that expands. Trust comes from seeing sources, not from a spinner.
3. **Every claim is openable.** Evidence chips open the quote with speaker, time and "Open call at 12:41".
4. **Nothing moves under the reader.** Reserve space while loading; animate height with measured values; reduced motion → opacity only (kernel rules S §2.3/§7).
5. **No decorative weight.** Content on paper, flat assistant text, glass only for floating chrome, no mascot, no bubble tails.
6. **Bilingual by construction.** Every string through `t.product.*`; the answer follows the user's language.
7. **Less UI, not more.** Prefer a default, an inference or an existing control over a new element (project rule). Where the Wizard adds a control (slash menu, mentions, suggestion grid), Vocify starts without it.

### 7.2 Anatomy

| Component | Responsibility |
|---|---|
| `AskShell` (drawer or `/dashboard/ask`) | Header: title "Preguntar a Vocify", context chip, history, new chat, close. Drawer 440 px, resizable 380–720, remembers width. Full page = history rail 260 px + thread `max-w-3xl`. Mobile: full-screen sheet with safe-area composer. |
| `AskContextChip` | "Marina López · Acme" for the page entity; removable. Says what Ask can see, in words, never JSON. |
| `AskHome` | One line of context, ≤2 insight rows **only when they say something Today does not already show**, ≤3 suggestion chips from real state (no playbook → "Set up your process"; no CRM → "Connect HubSpot"); role-aware (rep vs owner/admin). Skeleton reserves the row heights. |
| `TurnView` | User pill (right). Assistant block (left, no bubble): `ActivityLine` → `AnswerBody` → `EvidenceRow` → `CoverageNote` → `ActionRow` → `FollowupChips`. |
| `ActivityLine` | Live: one row per step (icon, label, spinner→check). Done: collapses to "Looked at 3 conversations · 2 CRM records", chevron expands. |
| `AnswerBody` | Markdown: headline semibold, prose 15/1.6, tables (`ResultTable`), tiny CSS bars for distributions (no chart library). |
| `EvidenceChip` | `[1]` inline; popover: quote, speaker, date, rep, "Open call at 12:41". |
| `ChoiceCard` | Disambiguation rows: name, company, last touch. Arrow-key navigation. |
| `ConfirmCard` | Target, action in plain words, field diff (before → after), text buttons **Confirm** / **Cancel** (not icon-only), result row. |
| `Composer` | Auto-grow textarea, existing `VoiceComposer`, send↔stop. No slash menu and no `@` mentions in V1: the context chip plus `ChoiceCard` resolve entities. Revisit after usage data. |

### 7.3 State matrix

| State | What the user sees | Notes |
|---|---|---|
| Empty | Greeting, insight cards, chips | No fake metrics, no fake history |
| Sending | User pill appears at once; assistant row reserved (72 px min) with "Entendiendo…" | Optimistic; `client_turn_id` fixed, double-click safe |
| Working | `ActivityLine` rows; state label | `aria-live=polite`, throttled |
| Streaming | Markdown appended per paragraph; no caret under reduced motion | Scroll follows only if the user is at the bottom, else "New answer ↓" |
| Complete | Evidence, coverage note, actions, follow-ups; copy and 👍/👎 always visible at low emphasis | 👎 asks one optional reason; both feed the eval set (D5) |
| Needs a choice | `ChoiceCard`, focus to first option | Superseded when the user types something else |
| Needs approval | `ConfirmCard`, inactive with a reason if contact or revision changed | Never a global "yes" |
| Executing | Button spinner | |
| Result | ✓ "Guardado en HubSpot" + link · ✗ "No se pudo guardar" + Retry · ? "Comprobando…" (`uncertain`) | Real write result only |
| Partial coverage | Note under the answer, fixed wording | Never "no activity" |
| Forbidden | "Los datos de equipo solo están disponibles para owners y admins." | Explains, does not go silent |
| Empty result | "Ninguna conversación coincide. Prueba otro periodo." + chips | |
| Long run (>30 s) | "Sigue en curso. Puedes cerrar y volver." | Polling drops to 5 s, no re-POST |
| Stream drop | "Reconectando… tu pregunta sigue en curso" then poll | |
| Error | Inline card, draft preserved, **Try again** | No toast spam |
| Session expired | "Vuelve a iniciar sesión" | Draft kept |

### 7.4 Visual spec (existing tokens only)

- **Type:** Geist. Body 15/1.6 (`THEME_TOKENS.typography.body` size), meta 13, floor 12. Tabular numerals in tables and metrics.
- **User pill:** `rounded-2xl bg-secondary/70 px-4 py-2.5` (as today). **Assistant:** no container.
- **Cards** (confirm, choice, insight): `bg-card border border-border/70 rounded-xl`, hover `border-beige/25`, press `active:scale-[0.98]`, 150 ms.
- **Primary button:** beige fill, `text-primary-foreground`, min height 36 px. Secondary: ghost. Destructive: `hover:bg-destructive/10`.
- **Composer:** `rounded-2xl border-border/70 bg-card shadow-sm`, focus `border-beige/40 ring-2 ring-beige/20`, sticky with safe-area.
- **Evidence chip:** `rounded-full bg-secondary/60 px-2 py-0.5 text-[12px]`, hover `bg-secondary`. Popover `shadow-sm`.
- **Tables:** `rounded-xl border`, header 13 px muted, numbers right-aligned, max 8 rows + "Show all".
- **Icons and controls:** reuse `IconAction` and the icon set Ask already uses (Phosphor `weight="light"`: `Check`, `PaperPlaneTilt`, `X`, `Microphone`). The rest of the dashboard uses lucide (65 files vs 6), so do not mix sets inside one component; add no new icon library. Shadows only on the composer and popovers.
- **Dark mode** through existing tokens. Contrast ≥ 4.5:1; focus ring 2 px; hit targets ≥ 36 px.

### 7.5 Interaction and accessibility

`Enter` sends, `Shift+Enter` newline, `Esc` closes the drawer (or aborts a running turn first), `↑` in an empty composer edits the last question, `Tab` order follows reading order, `role="log"` on the thread, `role="status"` on progress, focus returns to the trigger on close, popovers trap and restore focus. Entry points: sidebar **Preguntar**, plus **Ask about this** on memo detail, Today card and team view, each opening the drawer with a context chip and a seeded prompt.

### 7.6 Copy rules

Short, plain, no tool names or ids. Headline first. Spanish and English strings live in `t.product.*` (the Wizard hardcodes English in its warning cards; do not repeat that). Coverage and refusal wording is fixed text, reviewed once. Generated answers meet the project's "sin AI slop" criterion: short, specific to the contact, no assistant tone, no filler.

### 7.7 Proportionality declaration (per `no-extra-ui.mdc`)

| New element | Where | Visual weight | Why it earns its place |
|---|---|---|---|
| Thread with markdown, tables | Ask drawer/page | Main content | Answers are analytical; plain text lines cannot carry a table or a list |
| `ActivityLine` | Above the answer | Low: one muted line, collapsed when done | Trust and wait feedback; replaces a bare spinner |
| Evidence chips | Inline in the answer | Low: 12 px pill | The only mechanism that makes a claim checkable |
| `CoverageNote` | Under the answer | Low: 13 px muted, one line | Honest partial data; required by C08 semantics |
| `ConfirmCard` | In the turn | Medium, only when a write is proposed | Existing pattern (icon buttons) made explicit and unambiguous for writes |
| `ChoiceCard` | In the turn | Medium, only when ambiguous | Existing behaviour (`offer_user_choices`) already there; adds detail per row |
| History rail | Full page; a button in the drawer | Low; collapsed by default in the drawer | You asked to see chats and their summaries; needed once conversations persist |
| Copy, 👍/👎 | Answer footer | Low: icon-only `IconAction`, tooltip | Copy is basic; feedback feeds the eval set (D5) |
| Follow-up chips | Under a complete answer | Low, max 3, only when a skill defines them | One-tap next question; skipped when there is nothing useful |
| Insight rows on Ask home | Empty state only | Low, max 2, hidden if duplicated by Today | Gives the empty state something real instead of generic chips |
| **Not added in V1** | — | — | Slash menu, `@` mentions, mascot, suggestion grid, per-message bubbles, hover-only controls |

**Surface integration.** Dashboard: drawer plus `/dashboard/ask`, entry from the sidebar and "Ask about this" on memo detail, Today card and team view (a compact secondary link, not a new button per row). WhatsApp: same loop, text renderer. Extension and desktop: no Ask in V1; the plan already separates "anotar" from "preguntar" in the extension (D6).

---

## 8. Changes this design makes to the current plan

| Where | Change |
|---|---|
| `proposed_plan.md` §2 F07 row | Replace the "PERMITELO / simular Wizard" note with: real SSE, Wizard parity, persisted-turn recovery kept. |
| F07 §A9 | Streaming allowed; polling remains the recovery path. Confirm buttons become text buttons. |
| **C07** | Add `POST …/turns/stream` and the SSE contract; add `copilot_operations` (tool, args, target, revision, status, result); add `ask_conversations`. |
| **C04** | Fix contract/code drift (dateless commitments); add `response`, `t_ms`, `position`, `outcome`, `pain_points`, `competitor_mentions`, `stakeholders`; single merged producer. |
| **C19 / F15** | "Manager chat" is Ask with owner/admin scope, not a second engine. The registry (§5) is the single source for dashboard, report and chat. |
| F09 / F10 | F10's structured objections consume the objection episode; no separate interpretation. |
| Migrations | `050_ask_conversations_operations.sql`, `051_interaction_patterns_episode.sql`. Both additive. |
| Config | `ASK_MODEL`, `ASK_FALLBACK_MODEL`, model-profile table for reasoning params. |

---

## 9. Rollout (small deliverables, one at a time, each with its own gate)

| # | Deliverable | Size | Gate |
|---|---|---|---|
| 0 | **Spike:** streaming `tool_calls` on DeepSeek via OpenRouter; check the two flags and the G6 SQL on staging | S | Decision on model and on whether IntelligenceV2 starts by fixing the merge |
| 1 | **F07a Ask engine:** `AskActor`, persisted conversations and operations, confirm-bound-to-payload, SSE stream, per-surface model config | L | Double-submit, reload, restart and scale-out do not duplicate or lose a write; `uncertain` reconciles |
| 2 | **F07b Ask UI:** `AskThread` core, drawer + page, activity line, choice/confirm cards, composer, history rail | L | All §7.3 states verified with Reticle (`act_and_wait` / `assert`) plus keyboard, reduced-motion, contrast |
| 3 | **F07c Intelligence tools v1** (read-only, data that exists now): `deal_story`, `find_interactions`, `my_today`, `metric`, `objection_breakdown`, `playbook_lookup`, `team_roster`, `outcomes`, grounding contract and lint | M | Eval set, critical cases 100% |
| 4 | **F0.2 IntelligenceV2** (§4): merged producer, objection episodes, dateless commitments, competitors, stakeholders; backfill | L | Field-ownership tests; quote validation; 100% of v2 facts pass the substring check |
| 5 | **F07d Registry and manager tools:** §5 v2 metrics, `response_examples`, `prep_call`, `explain_score`; shared with F15 backend | M | Same numbers in Ask, dashboard and report for the same scope |
| 6 | **F07e Proactive:** insight cards, weekly readout, "promote to playbook" | M | Deterministic detection tests; no card below min sample |
| ∥ | **Eval harness** grows with every step; human review of critical cases | S each | Regression run before any model or prompt change |

Steps 3 and 4 can swap if the G6 check shows extraction is being overwritten; then fix the producer first.

**Verify G6 on staging (read-only):**

```sql
select
  count(*) filter (where extraction->'intelligence' is not null)                                   as with_block,
  count(*) filter (where extraction->'intelligence'->>'prompt_version' = 'intelligence_v1')        as llm_block,
  count(*) filter (where extraction->'intelligence'->'meeting'->>'agreed' is not null)             as jev_block,
  count(*) filter (where extraction->'intelligence'->>'prompt_version' = 'intelligence_v1'
                     and extraction->'intelligence'->'meeting'->>'agreed' is not null)             as both
from memos where created_at > now() - interval '30 days';
```

`llm_block > 0`, `jev_block > 0`, `both = 0` means the two writers are replacing each other.

---

## 10. Testing and evaluation

- **Engine (TDD, real Postgres for atomicity, as the plan requires):** replayed `client_turn_id`; confirm after restart executes the stored payload; changed contact → conflict and no write; `uncertain` reconciles; member cannot read team data through crafted ids or wording; tools a member may not use are absent from the model's tool list.
- **Grounding:** numeric-lint pass and fail; unknown evidence token stripped; coverage note for each of `complete/partial/forbidden/unavailable` is deterministic; language lint blocks causal verbs on `association` metrics.
- **Extraction:** every quote is a substring; dateless commitment kept and not turned into a Today signal; `deflected` vs `resolved`; merged producer never drops a field owned by the other.
- **UI (Reticle):** send → activity → streamed answer → evidence popover; stream drop → poll recovery; confirm → result and `uncertain`; forbidden and partial-coverage states; keyboard-only run; reduced-motion; dark mode; 375 px width.
- **Model eval:** §6.5. No default-model change without the report.

---

## 11. Decisions for you

| # | Decision | My recommendation |
|---|---|---|
| D1 | May Ask answer "who is lowest on X?" for owner/admin? The plan bans leaderboards. | Yes, as "needs attention on step X" with n, fixed alphabetical order, owner/admin only, only when asked. No default ranking widget. |
| D2 | May a *member* see a teammate's winning response to an objection? | No. Members see own calls plus manager-approved playbook examples. A manager can promote a real response into the playbook in one click. |
| D3 | DeepSeek V4 Flash and transcript quotes via OpenRouter, given `gdpr_dpa: false`. | Send DeepSeek quote-free aggregates; keep quote-bearing turns on a DPA-backed model until providers are pinned and a DPA is confirmed. |
| D4 | Chat retention and user deletion. | 90 days, user-deletable, never used for training. |
| D5 | Store 👍/👎 and reasons as eval data. | Yes, with the same retention, company-scoped. |
| D6 | Ask on extension and desktop in V1? | No. Web and WhatsApp only; blocks can reach `shared/ui` later. |
| D7 | Should I fix G2 (confirm without a write) as a separate small PR now, ahead of the redesign? | Yes. It is a correctness bug on a write path. |

## 12. Risks

| Risk | Mitigation |
|---|---|
| DeepSeek tool-call streaming is unreliable | Spike first; fallback model; non-stream path stays |
| Extraction v2 raises cost and latency per memo | Existing job queue, per-run cap, closed-vocabulary fields on the cheap classifier, measure before backfill |
| Numeric lint rejects valid answers | One retry, then deterministic table; log rejection rate as a metric |
| Metric definitions drift between surfaces | One registry, `definition_id@version` returned with every value, a test that dashboard/report/Ask agree |
| Scope creep into "everything a head of sales might ask" | Registry-first: a question that no metric answers gets an honest "I can't measure that yet", and becomes a candidate metric |
| Two live conversation stores (WhatsApp RAM, web DB) | WhatsApp memory moves to the same `ask_conversations` table in F07a |
