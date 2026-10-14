# Backend reliability plan: freezes, lost work, live service, worker

**Date**: 2026-10-14
**Status**: Plan to build on later. The freeze fix that shipped (bd0bb04a) is the current state. Nothing below this is built.
**Code read at**: `origin/main` 4c874309 (backend), `getvocify-desktop` `origin/main` 27b86bd.
**Builds on**: [Durable job queue and worker design](2026-10-14-durable-job-queue-worker-design.md) (c57a864c). That spec is the worker design; this plan is the inventory of what the worker and the rest of the work must cover, and the order.
**Security findings** are in a separate local file kept out of git while they are open (this repo is public): `docs/superpowers/specs/2026-10-14-security-findings-PRIVATE.md`.

How to read the evidence labels:
- **Verified**: checked directly (production logs, Twilio/HubSpot/Supabase reads, running the code, or reading the code myself).
- **From code reading**: a study agent's finding with file:line, not re-checked. Line numbers are at 4c874309 and will drift.
- **Estimate / unverified**: says so.

---

## 1. What happened and what is already fixed

### The incident (verified)
- 2026-10-14 17:36–17:42 CEST: a call from the desktop island (Twilio `CA8776306fa4e30bdbb57f0dae99dedf9d`, 343 s) produced no memo.
- At hang-up the API's event loop was blocked for 56 s (`event loop held for 56113 ms`). The live-transcript upload (20 s client timeout), Twilio `dial-status` (15 s) and Twilio `recording` (30 s) all ended 499. Nothing retried.
- That day the API froze 14 times for 5 s or more (worst 186 s at 12:43 UTC). CPU stayed under 0.15 vCPU over 8 h: the process was waiting on the network, not working.
- 10 more calls (Oct 7–8) and 1 more on Oct 14 16:12 had finished Twilio recordings that were never processed: no recording playback, no HubSpot call.

### Root cause (verified in supabase/postgrest 2.32 source)
- `backend/app/deps.py` reset `client._postgrest/_storage/_functions = None` on every `get_supabase()`. Every query built a new `httpx.Client(http2=True, timeout=120)` and never reused it.
- `PaywallMiddleware` (`backend/app/paywall.py`) ran 3 of those sync queries on the event loop for every authenticated `/api` request.
- One process, one event loop: one slow Supabase reply froze every user.

### Shipped (bd0bb04a, on main, deployed 2026-10-14 17:21 UTC)
- One shared httpx pool for PostgREST, storage and auth (HTTP/1.1, 5 s connect, 30 s read, 10 s pool).
- Paywall lookup in the threadpool, 60 s cache of "not paywalled" only, fails open past 5 s.
- No-await hot handlers made plain `def`: `/auth/me`, `/auth/refresh`, `/notifications`, `/calls/token`, `/calls/config`, `/calls/outbound/latest-disposition`, `/calls/history`, `/calls/{sid}`, `POST /captures`.
- Twilio `/recording` answers at once and processes in the background (one job per call); callback URL carries `#rc=5&rp=ct,rt,5xx` (Twilio's default retries only connect failures); `answered_at` from `RecordingStartTime`; `/dial-status` answers before logging; `/voice` queries from the threadpool.
- Call reconciler every 2 min (`backend/app/services/telephony/call_reconciler.py`, 24 h look-back).
- Island upload retries on timeout/5xx (`src/lib/transient-retry.ts`).
- Loop watchdog: logs the blocking line's stack when the loop is held over 2 s (`backend/app/services/loop_monitor.py`).
- Guard test `backend/tests/test_no_new_blocking_db_calls.py`: direct `.execute()` inside `async def` routes may only go down (114 at ship time).

Verified after deploy: the reconciler recovered the 16:12 call on its first sweep; the 10 Oct 7–8 calls were replayed (memo + recording + one HubSpot call each, HubSpot dates corrected by hand). First 9 min after deploy: 15 stalls, none ≥ 1 s, max 882 ms (pre-fix: 37 stalls ≥ 1 s in 2 h). That window is too short to judge; see §8.

### Done elsewhere, not on main yet
- **`6be91371`** (local commit, not pushed): HubSpot calls logged late keep their own date (`answered_at + duration`, missed calls `created_at`). Without it, any call processed late (retry, reconciler, replay) lands on the wrong day in HubSpot. Verified bug, verified fix (tests fail on old code).
- **`97292ea6`** (on `staging`, untested on staging.getvocify.com): a Vocify call memo stuck in `transcribing` is re-transcribed from its stored recording, at most twice.

---

## 2. Why "freeze" and "lost work" are two problems

- **Freeze**: the single event loop waits on something synchronous (supabase-py `.execute()`, a sync HTTP client, a sync storage upload, CPU-heavy work). Every request on that process waits. Fix: get the wait off the loop (threadpool now, async client later).
- **Lost work**: work held only in process memory (`asyncio.create_task`, `BackgroundTasks`) or answered "OK" before it is saved. A deploy, crash, timeout or swallowed error drops it silently. Fix: write the job down before answering, run it in a worker that retries and resumes.

Threads fix freezes and do nothing for lost work. The worker fixes lost work and, once background loops leave the API, makes running 2+ API processes safe (today every API process would run every periodic loop).

---

## 3. Remaining freezes (blocking work on an event loop)

The guard test counts 114 direct `.execute()` calls inside `async def` routes; many more sit inside helpers called from async code. All are now bounded by the 30 s client read timeout, so a single slow Supabase reply can still freeze a whole process for up to 30 s.

### 3.1 Background pipelines (from code reading)
| Path | What blocks | Runs |
|---|---|---|
| `extract_memo_async` (`api/memos.py:355-564`) | ~20–30 sync DB round trips: `update_memo_row` (400/489/503), selects (420-426), glossary, `load_extraction_llm_context`, `load_stt_profile`, `_read_call_first` + `call_context` (3 queries), `apply_reading_type`, `schedule_followup`, `record_enqueue`, `persist_pipeline_meta`, auto-approve select | per memo, every source |
| `run_post_extraction_hooks` (`services/memo_extraction_hooks.py:372-422`) | entirely sync, called from async: `select *` with full transcript, tag update, **`repin_before_c04` → sync `httpx.Client(timeout=3.0)` HubSpot/Pipedrive calls** (`services/playbooks/routing.py:31, 167-195`) when playbook routing is on, pattern upsert, score publish, meeting proposal | per memo |
| `prepare_transcript_for_extraction` (`services/transcript_sanitize.py:648-683`, called sync at `memos.py:452`) | regex per glossary term over the whole transcript (CPU) | per memo |
| `ensure_followup` (`services/followup.py:316-361`) | sync reads, preference, lease | per memo |
| `RecoveryService` (`services/recovery.py:37-41, 56`) | `select *` (all stuck transcripts) on the loop | every 5 min |
| Hoy confirm sweep (`services/hoy/confirmations.py:444-451, 321-337, 381`) | sync select/claim/update | every 60 s |
| CRM stale gauge (`services/crm_updates.py:341-347`) | sync count | every 5 min |
| `_memo_from_recording` / `initiate_vocify_call_memo` (`api/webhooks.py:959-962`, `services/telephony/call_processor.py:115-136`) | ~5 sync calls plus playbook pin queries | per Twilio call |

### 3.2 Inbound webhooks doing heavy work before answering (from code reading)
| Route | Before answering | Blocking on the loop |
|---|---|---|
| `/webhooks/whatsapp`, `/webhooks/unipile` (`api/webhooks.py:98, 171`) | the whole pipeline: profile, CRM resolve, conversation, media download, STT, storage upload, idempotency, field specs (may refresh HubSpot token), glossary, LLM extraction, memo insert, follow-up, deal search, preview send. ~25+ sequential network calls | sync `.execute()` (`services/whatsapp/processor.py:741-747, 2173-2179, 2238, 2249-2255`), `ConversationService` fully sync, **sync storage upload** `StorageService.upload_audio` (`services/storage.py:58-65`) |
| `/webhooks/hubspot` (`api/webhooks.py:350` → `services/hubspot/auto_sync.py:206-251`) | per event: scans **all** connected HubSpot connections in Python (`auto_sync.py:116-126`), token refresh, engagement fetch, members, memo insert; may run `approve_memo_core` inline | sync `.execute()` at `auto_sync.py:121, 136, 152, 287`, `services/hubspot/call_processor.py:71-77, 119, 160-176`, `token_refresh.py:101-107` |
| `/webhooks/recall` `bot.done`/`transcript.done` (`api/webhooks.py:1592+`) | ~10–15 calls: capture lookup, Recall `get_bot`, transcript download, calendar event, HubSpot attendee enrichment, capture completion, extraction start | sync DB (`services/meetings/recall_bot.py:88-96`, rep name/email reads) |
| `/webhooks/stripe` (`api/stripe_webhooks.py:65`) | ~5–9 calls incl. **sync `stripe.Subscription.retrieve`** (`stripe_webhooks.py:59`) | all sync inside `async def`; no Stripe SDK timeout set |
| `/public/hubspot/recordings/{id}` (`api/hubspot_recordings.py:26`) | 2 sync calls | sync `.execute()` + signed URL |
| OAuth callbacks (`api/crm.py:797`, `crm_salesforce.py:100`, `crm_pipedrive.py:102`, `calendar.py:171`) | 3–5 calls | sync company lookup/upsert |
| `/webhooks/telnyx/voice` (unused: `CALLING_PROVIDER=twilio`, verified) | `call.recording.saved` ~12–15 calls inline; sync Telnyx `get_recording`; HubSpot refresh with `threading.Lock` + sync httpx (`services/hubspot/oauth.py:232-245, 265-290`) | yes |

### 3.3 Request paths still blocking (from code reading)
- `api/coaching.py:391` calls sync `_rep_context` from `async def` and blocks on `ThreadPoolExecutor(...).result()` (`coaching.py:294-305`).
- `/copilot/suggest`: `load_contact_history` does a sync `.execute()` on the loop on a 120 s cache miss (`services/copilot/contact_history.py:23, 136-138`).
- `/copilot/checklist` (`services/copilot/checklist.py:126-141`), `/copilot/call-type/guess` and `/propose` (`services/copilot/call_type.py:46-61, 77, 187-190`), `/live-calls/preview` and `/start` via `_connected_account_id` (`api/live_calls.py:103, 135` → `services/company_scope.py:35, 44`), `_contact_name` (`api/crm.py:517, 551`).
- Re-transcribe downloads the recording synchronously (`api/memos.py:2761`, `services/storage.py:107-111`).

### 3.4 Vendor HTTP layer (partial; this study was stopped early)
- LLM: a new `httpx.AsyncClient` per attempt (`services/llm/providers/openrouter.py:233`), so no connection reuse; `MAX_RETRIES = 2`, `DEFAULT_TIMEOUT = 45 s`, **no backoff between non-streaming attempts** (`openrouter.py:31-32, 199-300`); worst case ~270 s per call. Vertex same pattern (`vertex_ai.py:27-28, 81-145`).
- Copilot turn: Jev client is a new `AsyncClient` per call (`services/llm/jev.py:72`), so a TLS handshake every turn on the live path; suggest also a new client per request (`services/copilot/suggest.py:229, 246`).
- HubSpot client: 3 retries, exponential backoff, honours Retry-After (`services/hubspot/client.py:40-42, 239-249`). Good.
- Not studied: full per-vendor client inventory, timeouts for every SDK, 429 handling outside HubSpot.

---

## 4. Lost or stuck work (no durable job, no recovery)

From code reading unless marked. "Ref" = the asyncio task object is kept referenced; 14 `create_task` sites keep none (`api/memos.py:620, 856, 2513, 2795, 2832`, `api/webhooks.py:491, 1276, 1439, 1565`, `services/hubspot/call_processor.py:181`, `services/recovery.py:111`, plus the four startup loops `main.py:395-398`). Nothing drains in-flight work on shutdown (`main.py:422-429`).

| # | Work (frequency) | What breaks | Recovery today |
|---|---|---|---|
| 1 | Memo extraction (per memo, every source; `memos.py:620`) | restart leaves `extracting`; the tail (post-extraction hooks, follow-up, C04, auto-approve) is lost and never redone; a failed extraction is terminal, no retry | `RecoveryService` re-queues `extracting` after 5 min, but `pipeline_lease` holds 600 s, so ~10–15 min; no attempt cap |
| 2 | Upload-audio STT (`memos.py:623-728, 856`) | audio only in memory: restart leaves `uploading` forever, or `transcribing` → marked failed | none; user re-records |
| 3 | WhatsApp voice notes (`processor.py:1871-1891, 2100-2285`) | the inbound message row is written first; a crash mid-pipeline makes the vendor's redelivery look like a duplicate and get skipped. Errors return 200 (`webhooks.py:158-168, 294-303`). | none |
| 4 | Recall meeting notes (`webhooks.py:1729-1802`) | a transient transcript fetch failure marks the memo failed **and returns 200**, so Recall never retries; captures in `uploading` are never swept; a >15 s first attempt can run concurrently with Recall's retry | none |
| 5 | Twilio call: recording stored, memo not yet made | the reconciler only looks at `status='dialing'` with no `recording_path` (`call_reconciler.py:41-43`); a crash in that window loses the memo silently. **Verified: a gap in the reconciler shipped in bd0bb04a.** | none |
| 6 | Call memo in `transcribing` | `RecoveryService` marks it failed with "Audio is not stored" although the WAV is in storage (`recovery.py:70-78`) | fixed on staging by `97292ea6` |
| 7 | C04 intelligence / coaching publish (`services/intelligence/extract.py:915`) | lost on restart; `worker.sweep_missing` (`worker.py:278`) is never called | manual admin backfill only |
| 8 | CRM auto-approve after extraction (`memos.py:541`, `services/hubspot/auto_sync.py:270, 312-318`) | lost on restart, errors swallowed | user approves by hand |
| 9 | Follow-up draft (`followup.py:352-358`) | restart leaves `generating`; an error means permanently `unavailable` | regenerates only when someone opens the memo after 4 min |
| 10 | HubSpot call processing (`services/hubspot/call_processor.py:181`) | restart → recovery marks failed | webhook redelivery or the extension button |
| 11 | Stripe event with an unresolved company (`stripe_webhooks.py:46-62, 106`) | `_apply_event` returns, then `claim_event` marks it processed: dropped for good. Out-of-order `customer.subscription.*` events overwrite newer state (no timestamp guard) | none |
| 12 | Ask / MCP ask turns (`api/ask.py:341`, `services/mcp/ask_runs.py:148`) | stuck `pending`/`running` forever | none |
| 13 | Usage ledger rows, admin reprocess/backfill progress | lost | none |

Already durable: Hoy confirm CRM writes (claim + 10 min lease + 3 attempts, `confirmations.py:30-32, 306-451`), report emails (delivery rows + Resend idempotency key), Twilio recordings before `recording_path` is saved (reconciler + Twilio retries), extraction's own step (time-based re-queue).

---

## 5. Concurrency and load

- **No global cap** on extractions, STT or LLM calls (from code reading). Only small semaphores: preview prewarm 3, transcript patch 4 chunks, C04 backfill 3, crm_query copilot 4. **Estimate**: 20 memos finishing at once → ~100–200 concurrent LLM requests and 20 × 20–30 sync DB round trips serialized on the loop.
- Provider 429s on non-streaming LLM calls are retried immediately, then the memo fails.
- The existing memo_jobs worker is the opposite extreme: one job per 30 s pass.
- **Verified**: CPU averaged ~2% of one core, max ~15%, over 8 h on 2026-10-14. The backend is not overloaded; it waits.
- Client polling (verified in production HTTP logs, ~1 h, 1–2 users, pre-fix): `/auth/me` ~123/h, `/notifications` ~116/h, `/crm/hubspot/companies/{id}/recordings` ~68/h, `/calendar/upcoming` ~56/h, `/memos/{id}/brief` ~40/h, `/crm/hubspot/recordings` ~37/h, `/calls/{sid}` ~29/h, `POST /live-calls/preview` ~30/h. Post-fix latency still high per request: `/notifications` p50 ~560 ms, `/auth/me` up to ~880 ms (verified, small sample). The client-side study was stopped; which components poll and whether they stop when hidden is not mapped.

---

## 6. The live service (`app.live_main`, Railway service `live`)

From code reading unless marked.
- **No freeze monitor (verified)**: `live_main.py` startup only validates config; `loop_monitor` is not started, so the live service's freezes are invisible.
- No sync DB/HTTP per audio chunk or per transcript turn. Session start reads run in a thread (`api/transcription.py:543`).
- **CPU on the loop per call**: JSON + base64 per 100 ms chunk; with `aec=1` the AEC3 Python loop and np concatenations plus a 131072-point FFT every 1–3 s (`services/echo_canceller.py:153-262`); with MAI (`LIVE_STT_PROVIDER=mai`, **verified** in prod vars) a pure-Python per-sample `Upsampler` and `speech_level` (`services/live_channel_sessions.py:553-609`); `apply_glossary` per partial rebuilds and runs one regex per alias (`transcript_sanitize.py:124-152`). **Estimate**: ~60–100 concurrent calls per process without AEC, ~15–35 with AEC, ~10–25 with MAI. Turning on the loop monitor replaces these guesses with numbers.
- **Every deploy drops every live call**; the desktop reconnects (5 tries, linear backoff, `DesktopMeetingProvider.tsx:160, 578-590`) but audio sent while the socket is not OPEN is dropped (`:1244-1250`), and language detection and echo learning restart.
- **Silent STT stall is undetected**: a provider that stays connected but stops sending results ends that side's transcript for the rest of the call; `_send` waits on `ready` with no timeout (`live_channel_sessions.py:363`).
- **Split-brain `live_activity`**: written by `live` (`live_channel_sessions.py:830, 837`), read by the API's Twilio recording path (`api/webhooks.py:914`). In different processes `recently_live` is always False, so the recording never waits for the live transcript; the two memos race and one is deleted (`call_memo_claim.py:34-58`), and batch STT + LLM is spent on calls that already had a live transcript.
- Desktop reconnect counter resets on `onopen` before auth (`DesktopMeetingProvider.tsx:525`): a rejected ticket reconnects forever.
- Unbounded growth: `LiveStream.queue` (`live_channel_sessions.py:317`), `LiveReport` lists (`services/live_report.py:42-121`), `self.streams` (`:856`).
- The legacy `/api/v1/transcription/live` route is still served **by the API** (web recorder `src/features/recording/hooks/useRealtimeTranscription.ts:187-191`, Chrome extension `chrome-extension/background.js:552`), sharing the API loop; on a Speechmatics error the client socket stays open with an unbounded queue (`api/transcription.py:353-363, 382, 412-448`).
- Desktop live STT cost is never attached to memos (no `capture_id` in `src/lib/copilot-channel-stt.ts:12-23`); the usage ledger is never flushed on shutdown.

---

## 7. The worker: what it must carry

Design: [Durable job queue and worker](2026-10-14-durable-job-queue-worker-design.md). It recommends a `jobs` table claimed through a PostgREST RPC (`FOR UPDATE SKIP LOCKED` + lease + fencing run id) over DBOS, because Vocify has no direct Postgres connection (**verified**: no DSN in Railway vars, no Postgres driver in `requirements.txt`).

### The existing base (verified + from code reading)
- `memo_jobs` (`migrations/039_memo_intelligence_jobs.sql`): `claim_memo_job` with `SKIP LOCKED` and a lease, `publish_memo_job` fenced by `run_id` with per-revision supersede. Sound and reusable.
- Its worker is gated by `INTELLIGENCE_WORKER_PUBLISH` (default `False`, `config.py:279`), **not set in production (verified)**. Rows are enqueued on every extraction anyway: **341 `pending` rows, never claimed (verified 2026-10-14)**.
- Gaps before reuse: no failed state or backoff RPC, no max attempts (a poison job retries forever at the front of the queue), one job per 30 s, no heartbeat or lease extension, `REGISTERED_KINDS = {'intelligence'}`, `sweep_missing` unused.
- Decide: claim the 341 rows, or close them as superseded.

### Job kinds, ordered by risk (from §4)
1. Webhook intake: save the event + a job row, answer 200 at once. WhatsApp/Unipile, Recall `bot.done`/`transcript.done`, HubSpot recording events, Stripe. Mark "seen" only on success.
2. `call_recording` + `call_memo` (Twilio), replacing the in-process job and covering the reconciler gap (§4 #5).
3. `extract_memo` and its tail as separate idempotent steps: post-extraction hooks, follow-up, C04/coaching, auto-approve.
4. `hubspot_call_log` (answered and missed), adopting an existing HubSpot call by `hs_call_external_id` on retry.
5. Upload-audio STT: store the audio before answering, then a job.
6. Periodic loops (memo recovery, confirm writes, CRM gauge, report tick, call reconciler, intelligence) move to the worker process.

### Worker rules
- Concurrency caps per kind (LLM-heavy kinds especially), so a batch can't fire hundreds of LLM calls.
- Max attempts with backoff, then `failed` + an alert (ERROR log → Sentry, as the CRM stale gauge does). Nothing retries forever, nothing fails silently.
- Every handler idempotent (the claim fences the run; external writes look up before creating).
- Separate Railway service from the same image, second start command (precedent: `backend/railway.live.json`). Graceful SIGTERM: finish or release the lease.

---

## 8. Finish line (measurable from production)

Proposed; not yet agreed:
1. **No freezes**: zero `event loop held` stalls ≥ 250 ms caused by our blocking code, for 7 days, in both `getvocify` and `live` (the monitor's own threshold).
2. **No silent loss**: every background job ends `succeeded` or visibly `failed` after retries with an alert; nothing held only in memory; no event answered 200 and dropped.
3. **Safe to scale**: the API runs as ≥ 2 processes with no duplicated background work.

Measuring 1 needs the watchdog's stack dumps over real traffic; the 9-minute post-deploy window is not evidence.

---

## 9. Build order

1. **Security fixes** (see the private file). Small, no design needed.
2. **Push `6be91371`** (HubSpot late-call dates). Test `97292ea6` on staging, then merge.
3. **Close the reconciler gap** (§4 #5): also sweep `status='recorded'` rows with a `recording_path` and no `memo_id`, re-running memo creation from the stored WAV.
4. **Measure**: start `loop_monitor` in `live_main`; collect a week of stalls and stack dumps from both services.
5. **Helper sweep** (stops freezes; mechanical, suits a cheaper model with review):
   - turn remaining no-await `async def` routes into `def` (run the loop-usage scan first: anything calling `create_task`/`get_running_loop`, e.g. `schedule_followup`/`schedule_intelligence`, must stay async);
   - offload the sync DB/HTTP in §3.1–3.3 with `run_in_threadpool`/`asyncio.to_thread`, starting with extraction, post-extraction hooks (incl. the sync CRM httpx in routing), WhatsApp, HubSpot and Recall webhooks, Stripe, and the copilot live paths;
   - offload live-service CPU: one compiled alias regex per session, AEC on a per-session thread, vectorized upsampler;
   - lower the guard test's counts as each file is fixed.
6. **Worker phases** per the job-queue design (§9 there): jobs table → worker service with a no-op job → call kinds → HubSpot logging → extraction + crons → remove in-process paths. Kinds in §7 order.
7. **Then**: run the API as 2 processes; reuse LLM clients; move the busiest routes to the supabase-py async client (`acreate_client`/`AsyncClient` exist in 2.32, verified).
8. **Live service resilience**: client audio buffering across reconnects, STT stall watchdog, fix `live_activity` split-brain, bounded queues, graceful drain on deploy.

---

## 10. Scope

**In**: the API, the `live` service, every inbound webhook, background work (extraction and its tail, follow-ups, coaching, auto-approve, the 341 stuck intelligence jobs), and client retry behaviour where it affects lost work.

**Out**: reducing dashboard polling (efficiency, not reliability; revisit later), Telnyx (production uses Twilio), microservices, Redis/RabbitMQ, DBOS for now, multi-region.

---

## 11. Open decisions

From the job-queue design (§10 there):
1. Jobs table over DBOS.
2. When the worker is down, calls wait (no in-process fallback once a kind's flag is on).
3. Alert threshold for a waiting `call_recording` job (proposed 3 min) and where it goes.
4. A staging TwiML app, so call changes can be tested on staging (today staging calls are processed by production).

New:
5. The 341 pending `memo_jobs`: claim or supersede.
6. The finish line in §8.
7. Whether the legacy API live-transcription route (web recorder, Chrome extension) moves to the `live` service or is retired.

---

## 12. Not verified

- Vendors' real retry/timeout behaviour (only repo comments: Recall gives up after 15 s and retries on non-2xx; Meta and Unipile deliver at least once). Stripe, HubSpot and Speechmatics unverified.
- Which Stripe webhook URL is registered (`/webhooks/stripe` in code, `/api/v1/webhooks/stripe` in a skill doc).
- Whether HubSpot v3 webhook signatures match behind Railway's proxy.
- Live DB schema details: a `crm_type` column used by `meetings/attendees.py:119` but absent from migrations (attendee enrichment probably never runs); a GIN index on `outbound_calls.provider_state`.
- All timing, capacity and concurrency numbers marked as estimates.
- The vendor-client and client-polling studies were stopped partway; §3.4 and the polling part of §5 are incomplete.
