# Vocify MCP server — design spec (2026-10-14)

Status: built 2026-10-14 (backend, settings UI, consent page, tests). Classified as a **big change** (auth + migration): it ships on `staging` first. "Decisions after the build" at the end records where the build settled what this spec left open.

## Problem Statement

Reps and sales managers already live inside their own AI agent (Claude, Cursor, ChatGPT, Claude Code). Everything Vocify captures — interactions, what was promised, objections, outcomes, coaching against the playbook — is only reachable inside the Vocify dashboard, extension or desktop app. To prep for a meeting, review a week or coach a rep from their agent, they have to copy and paste from Vocify by hand. There is no way for their agent to read their Vocify data: no API keys, no OAuth, no public API.

## Solution

A remote MCP server on the existing API (`/mcp`, Streamable HTTP, stateless) that a user connects to their agent in one of two ways:

1. **API key** — the user generates a personal key in Settings and pastes it into Claude Code, Cursor, Claude Desktop (via `mcp-remote`) or their own scripts.
2. **OAuth sign-in** — the user pastes the server URL into ChatGPT or Claude.ai and signs in with their Vocify account; no key involved.

Either way the agent gets five read-only tools, and sees exactly what that user sees in the dashboard (a rep their own interactions, a manager their team). Vocify prepares each interaction as one complete, agent-ready record; the user's agent does the synthesis. For aggregate questions whose numbers must match the dashboard, the agent can ask Vocify's own Ask engine.

Tools: `list_interactions`, `get_interaction`, `get_coaching`, `ask_vocify`, `get_ask_result`.

## User Stories

Connecting
1. As a rep, I want to generate a personal API key in Settings, so that I can connect Claude Code or Cursor to my Vocify data in one paste.
2. As a rep, I want the key shown exactly once with a copy button, so that it is not left visible on screen.
3. As a rep, I want to see that I have a key (its prefix and creation date) without seeing the key itself, so that I know which key is active.
4. As a rep, I want to regenerate my key, so that a leaked key stops working immediately and I get a new one.
5. As a rep, I want to revoke my key without creating a new one, so that I can disconnect every agent at once.
6. As a rep, I want copy-paste setup snippets for Claude Code, Cursor and Claude Desktop next to my key, so that I don't have to read MCP docs.
7. As a ChatGPT user, I want to add Vocify by URL and sign in with my Vocify account, so that I can connect without any key.
8. As a Claude.ai user, I want to add Vocify as a custom connector and sign in, so that it works on web, desktop and mobile.
9. As a user signing in through OAuth, I want a consent screen that names the app asking for access and says it is read-only, so that I know what I'm granting.
10. As a user, I want to see which apps I connected through OAuth and disconnect any of them, so that I stay in control.
11. As a user whose session or key is invalid, I want my agent to get a clear "sign in again / key revoked" error, so that I know what to fix.

Workspace control
12. As a workspace owner or admin, I want MCP access to be off until I turn it on for the workspace, so that nobody exports data before I decide.
13. As an admin, I want to see which members have an API key, so that I know who is connected.
14. As an admin, I want to revoke any member's key, so that I can cut access when someone leaves or a key leaks.
15. As an admin, I want a member who is removed from the workspace to lose MCP access on their very next request, so that offboarding is instant.
16. As an admin, I want to decide whether full transcripts are available through MCP or only summaries and quotes, so that I meet my data-handling obligations.
17. As an admin, I want MCP to respect my plan, so that a workspace without the entitlement cannot use it.

Reading interactions
18. As a rep, I want my agent to list my recent interactions with date, contact, company, kind, outcome and a short summary, so that it can find the one I mean.
19. As a rep, I want to filter interactions by date range, contact, deal, kind (call, meeting, visit, voice note) and outcome, so that my agent fetches only what matters.
20. As a rep, I want to filter by objection category, so that my agent can find every call where pricing came up.
21. As a rep, I want a free-text filter over contact, company and summary, so that "the Acme call" works without an id.
22. As a rep, I want each listed interaction to already carry its objection categories, competitors, outcome and coaching score, so that my agent can answer "what came up this week" without opening every call.
23. As a rep, I want my agent to open one interaction and get the summary, commitments, next steps, objections with the playbook's approved answers, competitors, outcome, coaching feedback and evidence quotes with timestamps, so that it can prep me or draft a follow-up.
24. As a rep, I want the transcript only when my agent asks for it, so that normal questions stay fast and cheap.
25. As a rep, I want long transcripts returned in pages, so that my agent's context window doesn't overflow.
26. As a rep, I want every interaction to carry a link back to the Vocify dashboard, so that I can open it myself.
27. As a rep, I want CRM ids on each interaction, so that my agent can match it with my HubSpot MCP connection.
28. As a rep, I want results paged with a cursor, so that my agent can walk through a long history reliably.
29. As a rep, I want interactions still processing or failed to be left out, so that my agent never reasons over half-built records.

Coaching
30. As a rep, I want my agent to get my coaching summary for a period (what I kept doing, what to fix, playbook adherence), so that I can ask "how am I doing this month".
31. As a manager, I want my agent to get the team view (adherence per rep, objections, activity), so that I can prep a 1:1 or a team review.
32. As a manager, I want to get one rep's coaching, so that I can coach that person specifically.
33. As a rep, I want coaching numbers through MCP to be identical to the dashboard's, so that my agent and Vocify never disagree.
34. As a rep (not a manager), I want team tools hidden from my agent, so that it doesn't try and fail.

Ask Vocify
35. As a manager, I want my agent to ask Vocify an aggregate question ("top objections this month across the team"), so that I get the same answer the dashboard's Ask gives.
36. As a user, I want a quick question answered in the same call, so that simple asks feel instant.
37. As a user, I want a slow question to return a run id that my agent can check later, so that it never hits a client timeout.
38. As a user, I want Ask answers to cite the interactions they used, so that my agent can open them with `get_interaction`.
39. As a user, I want Ask through MCP to never write to my CRM, so that an agent (or text inside a transcript) can't change records.
40. As a user, I want each Ask question answered on its own, so that my agent's own conversation is the only memory.
41. As a user, I want a clear error when Ask is unavailable (limits reached, model provider down), so that my agent falls back to the list/get tools instead of inventing an answer.

Safety and limits
42. As a workspace owner, I want per-user rate limits and a monthly Ask cap, so that a looping agent can't burn our quota.
43. As a user, I want rate-limit errors to say when I can retry, so that my agent can back off.
44. As Vocify, I want every tool call logged with user, workspace, tool, latency and outcome, so that we can debug and audit usage.
45. As Vocify, I want all tools marked read-only, so that clients don't ask for write approval and directories accept the listing.

## Implementation Decisions

Endpoint and transport
- Mounted at `/mcp` inside the existing FastAPI API service (`api.getvocify.com/mcp`; a `mcp.getvocify.com` domain may point at the same service). Not a separate service until load requires it.
- Official `mcp` Python SDK, exact version pinned. Streamable HTTP, stateless (the 2026-07-28 spec removed protocol sessions). The server must also negotiate the 2025-11-25 protocol, because clients are not confirmed on 2026-07-28 yet.
- `/mcp` sits outside `/api/`, so the existing paywall middleware does not see it: the MCP layer checks the plan entitlement itself. It must be exempt from the 30s timeout middleware (Ask has its own wait budget instead).
- All Supabase calls inside tool handlers run off the event loop (worker thread), so agent traffic cannot block the API.

Authentication: one resolver, two credentials
- A single dependency turns the `Authorization: Bearer …` header into the existing `Membership`:
  - Token starting with `vk_` → API key path.
  - Anything else → OAuth access token path.
  - Both end in the same `Membership`, so tools, scoping, limits and logging never know which credential was used.
- On every request, after resolving: membership is active, the workspace's MCP flag is on, and the plan allows it. Otherwise 401/403 with a message the agent can relay.
- Unauthenticated requests get `401` with `WWW-Authenticate: Bearer resource_metadata="…"`. Claude ignores this header on a 200.

API key (no new table)
- One key per user, stored as columns on `user_profiles`:
  - `api_key_hash` (SHA-256 of the key, unique index for lookup)
  - `api_key_prefix` (first characters, for display)
  - `api_key_created_at`
- The key is `vk_` plus a long random secret. Generated server-side, shown once, never stored in clear. SHA-256 (not a password hash) is enough because the secret is random.
- Regenerate overwrites the three columns. Revoke clears them. An admin revoking a member's key clears that member's columns.
- Profile (not workspace) because scoping is per user. A workspace-wide key would carry no identity, so it would either see everything or need its own permission rules. Claude's own docs say an org-wide header credential must not be used to identify the user.
- Endpoints: generate/regenerate, revoke, and status (prefix + created_at) for the caller; list members-with-key and revoke for owner/admin.

OAuth layer
- Supabase Auth's OAuth 2.1 server is the authorization server. Vocify's API is the resource server.
- Vocify serves the Protected Resource Metadata document, whose `resource` is exactly the MCP URL users paste and whose first `authorization_servers` entry is the Supabase issuer.
- Dynamic Client Registration is enabled in Supabase. Supabase does not document CIMD, and Claude falls back to DCR when CIMD isn't advertised.
- A consent page in the React app (Supabase hosts none). It shows the client name and the redirect host, and says the access is read-only.
- A "Connected apps" section in Settings to list and revoke OAuth grants.
- Access tokens are validated against Supabase's JWKS: signature, expiry, and audience (see the verification gate below).
- Verification gate, to settle on staging before building on it. Supabase's docs don't confirm any of these:
  1. which key signs OAuth tokens, compared with the HS256 secret the API checks today
  2. whether tokens can be audience-bound to the MCP URL (RFC 8707 `resource`)
  3. whether port-agnostic loopback redirects work for Claude Code
  4. how grants are revoked
  5. the feature's beta/GA status

  Gate passes when Claude.ai and ChatGPT developer mode both connect end-to-end. If it fails, a different authorization server is chosen before continuing. The API-key path does not depend on this gate and can ship first.

Tools (all read-only, `readOnlyHint: true`, `openWorldHint: false`, each with a `title`)
- Every tool runs through the same `AskActor` scoping the dashboard's Ask uses: a member sees only themselves, managers (owner/admin or team visibility) see the team. A `user_id` outside scope returns a forbidden error, not empty data.
- The tool list is the same for every caller (deterministic, as the spec asks). `get_coaching(scope=team)` and `rep_id` filters return a forbidden error to a rep.
- Errors are tool results with `isError: true` and say what to do next (e.g. "no interaction with that id; use list_interactions").
- Responses are concise by default and stay well under Claude Code's 25,000-token tool output cap.

`list_interactions`
- Filters: `from`, `to`, `rep_id` (managers), `contact_id`, `deal_id`, `kind`, `outcome`, `objection_category`, `q` (case-insensitive match over contact, company and summary), `cursor`, `limit` (default 20, max 50).
- Only usable statuses. Internal motions excluded, same rule as Ask's memo loading.
- Each row: id, started_at, kind, contact/company names, rep name, duration, outcome, one-line summary, objection categories, competitors, coaching score if scored, dashboard URL. This is enough to count and group without fetching each one.
- Returns rows plus an opaque `next_cursor`.

`get_interaction`
- Input: `id`, `include_transcript` (default false), `transcript_cursor`.
- Returns the interaction record:
  - summary, commitments and next steps, objections with the playbook's approved answer, competitors, outcome
  - coaching (kept, fix, adherence from the debrief), evidence quotes with timestamps
  - CRM ids, dashboard URL
  - transcript pages when asked and the workspace allows transcripts

The interaction record
- One serializer module turns a memo (plus its score, debrief, patterns) into the record. MCP uses it, and the dashboard API may use it later.
- "One fact, one producer": it reads what the screens read and never re-derives coaching.

`get_coaching`
- Inputs: `period` (week, month, last_30, quarter), `flow` (sdr/ae, optional), `user_id` (managers only), `scope` (`me`/`team`, team for managers only).
- Wraps the existing coaching summary and team adherence producers, so numbers equal the dashboard.

`ask_vocify` / `get_ask_result`
- `ask_vocify(question)`: the question is capped at 4000 characters, the same as web Ask. It runs the existing Ask engine:
  - all write tools and call actions removed
  - same scoping
  - a fresh conversation per question; no follow-up memory, the caller's agent keeps context
- Waits up to a fixed budget (about 20s). If finished it returns `{status: completed, answer, evidence, coverage}`. Otherwise it returns `{status: running, run_id}`.
- `get_ask_result(run_id)` returns `running | completed | failed` plus the answer. The run is stored as an Ask turn, so polling reads the stored turn status. Runs must not appear in the user's web Ask history; how they are tagged is an implementation detail to settle during the build.
- Provider failures (out of credit, 402, timeouts) return a clear error telling the agent to use `list_interactions`/`get_interaction` instead.

Limits and logging
- Per-credential rate limit keyed by user, not IP. slowapi is already a dependency; today it is used only on one auth endpoint, keyed by IP.
- A monthly Ask cap per workspace. The numbers are an open decision.
- One structured log line per tool call: user, workspace, tool, latency, outcome, credential type. No new audit table in v1.

Schema changes
- `user_profiles`: `api_key_hash` (unique), `api_key_prefix`, `api_key_created_at`.
- Workspace switches use the existing `company_feature_flags` mechanism (an MCP flag, and a transcripts flag). No new columns on `companies`.

## Testing Decisions

- A good test drives the public MCP endpoint the way a client does and checks what comes back. It never asserts on internal helpers.
- **One seam: the `/mcp` HTTP endpoint**, called in-process with FastAPI's `TestClient`, a fake Supabase and dependency overrides. Through that seam:
  - Auth:
    - no header returns 401 with `WWW-Authenticate` pointing at the metadata URL
    - a valid key returns tools
    - regenerated, revoked or wrong keys return 401
    - a removed member returns 401/403
    - workspace flag off returns 403
    - an OAuth token resolves to the same user as that user's key
  - Scoping:
    - a rep can't read a teammate's interaction (forbidden)
    - a manager can
    - `tools/list` differs by role
  - Tools:
    - list filters and cursor paging
    - excluded statuses and motions never appear
    - `get_interaction` without transcript, with paged transcript, and with transcripts disabled by the workspace
    - `get_coaching` returns the producer's numbers unchanged
  - Ask:
    - quick path returns an answer
    - slow path returns `run_id`, then `get_ask_result` completes
    - write tools are never offered to the engine
    - provider failure returns the fallback error
  - Limits: over the rate limit returns a retry hint.
- The OAuth discovery document and consent flow are verified manually against Claude.ai and ChatGPT developer mode during the verification gate. A unit test can't prove a third-party client connects.
- Prior art: `tests/crm_copilot/test_ask_http.py` and `tests/test_after_call_http.py` (HTTP through `TestClient` with a fake Supabase and `get_membership` overrides), `tests/crm_copilot/fakes.py`, and `tests/crm_copilot/test_actor_scope.py` (scoping rules).
- Ask answer quality through MCP reuses the existing `backend/evals/ask` harness. No new eval framework.

## Out of Scope

- Write tools of any kind (CRM notes, tasks, contacts, deals), and call actions.
- Proxying HubSpot/Pipedrive data as tools; users connect HubSpot's own MCP server for CRM records.
- A CLI.
- Several keys per user, key scopes, key expiry, `last_used_at` tracking.
- Full-text or vector search (v1 text filter is a simple match).
- MCP resources, prompts, MCP Apps UI, sampling and elicitation.
- Listing in the Claude connector directory, ChatGPT app directory or MCP Registry (follow-up once OAuth passes the gate).
- Follow-up memory across `ask_vocify` calls.

## Further Notes

- Open decisions for Dani:
  1. rate-limit and monthly Ask cap numbers, and whether they differ by plan
  2. whether Ask through MCP may run live HubSpot queries, which spend the customer's HubSpot rate limit
  3. whether transcripts are on or off by default when a workspace enables MCP
  4. the final URL: `api.getvocify.com/mcp` or `mcp.getvocify.com/mcp`
- Client facts behind the two credentials (vendor docs, checked 2026-10-14):
  - ChatGPT accepts OAuth 2.1 + PKCE only and cannot present API keys.
  - Claude.ai's header credential is beta, limited to some organizations, and org-wide.
  - Claude Code, Cursor and `mcp-remote` accept a bearer header.
  - So keys cover developer clients and OAuth covers ChatGPT/Claude.ai.
- The landing copy (`src/lib/landing-mcp.ts`) promises ChatGPT. That is only true once the OAuth layer ships.
- Reference: Sybill's MCP server (`mcp.sybill.ai/mcp`, OAuth, 8 read tools including an async `ask_sybill` + `get_ask_sybill_result`) is the closest comparable design.
- Related: [2026-09-28 Ask Vocify intelligence design](2026-09-28-ask-vocify-intelligence-design.md) for the Ask engine, scoping and the `gdpr_dpa` open decision, which also applies to transcripts leaving through MCP.

## Decisions after the build (2026-10-14)

- URL: `api.getvocify.com/mcp` (Dani). The server takes it from `BACKEND_PUBLIC_URL` + `/mcp`, so staging must set `BACKEND_PUBLIC_URL` to its own URL.
- Ask through MCP may run live HubSpot queries (Dani), within its own limits: at most `MCP_ASK_MAX_ROUNDS` (8) rounds a question, `MCP_ASK_PER_DAY` (30) questions a user per rolling 24 h, counted from the stored turns so it holds across instances.
- Every tool call: `MCP_TOOL_CALLS_PER_MINUTE` (60) per user, per server instance. All four numbers are env settings, chosen as starting values, not measured.
- Transcripts default off (`MCP_TRANSCRIPTS_ENABLED`); MCP itself defaults off (`MCP_ENABLED`). Both are per-workspace rows in `company_feature_flags`, switched by an owner or admin in Settings → AI agents.
- A bad, regenerated or revoked key is a 401. A removed member, a workspace with MCP off, or a paywalled plan is a tool error the agent can relay, not a 401 (a 401 would send the client into a sign-in loop).
- OAuth tokens are verified with the project's JWT secret (HS256) or its JWKS (RS256/ES256). The audience is not checked, because Supabase does not document what `aud` its OAuth tokens carry. The `role` claim must be `authenticated`.
- The consent screen is `/oauth/consent` in the dashboard. Its calls go through `/api/v1/oauth/*`, which forwards them to Supabase Auth with the user's own session token (the dashboard does not use supabase-js). The endpoints were read from `@supabase/auth-js` 2.117.3.
- Supabase dashboard settings Dani has to make, for the OAuth half only:
  - Authentication → OAuth Server: enable it, with Authorization Path `/oauth/consent`.
  - Turn on dynamic registration.
  - Site URL is the dashboard origin that serves `/oauth/consent`.
- Migration `079_mcp_api_keys.sql` adds the three key columns to `user_profiles`. Until it runs, creating a key fails and every key is invalid.
