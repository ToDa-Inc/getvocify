# Durable Job Queue and Worker — Design

**Date**: 2026-10-14
**Status**: Draft for Dani's review. No code yet.
**Follows**: bd0bb04a, "a slow Supabase reply no longer freezes every request, and a call's memo is never lost" (on `origin/main`, deployed 17:21 UTC).

---

## 1. Why

On 2026-10-14, synchronous Supabase calls held the API's event loop for up to 186 s. A desktop Twilio call ended during a 56 s stall, and it never got a memo. bd0bb04a fixed the stalls and added safety nets: Twilio webhooks answer at once and retry, a call reconciler runs every 2 min, the island retries its upload, and a loop watchdog plus a guard test catch blocking calls.

The background work itself is still not durable. It runs as `asyncio` tasks inside the API process, so a deploy, crash or OOM loses whatever was running:

| Work | Where it starts today | What a restart loses | What brings it back today |
|---|---|---|---|
| Call recording → memo | `webhooks.start_recording_job` → `_spawn(process_call_recording)` | everything after the 204 | Call reconciler, but **only** while the call is still `dialing` with no `recording_path` (see §1.1) |
| Call memo transcription | `_spawn(process_vocify_call_background(…, audio_bytes, …))` (audio held in memory) | the memo | Nothing. `RecoveryService` marks `transcribing` memos `failed`: "Audio is not stored. Please record again." For calls, the WAV **is** stored (`recording_path`). |
| HubSpot call logging | `_spawn(log_call_engagement)`, `_spawn(_log_missed_call)` | the HubSpot call | Nothing for answered calls; the reconciler, for missed calls still `dialing` |
| Extraction | `memos.start_extraction_from_transcript` → `asyncio.create_task(extract_memo_async)` | latency only | `_periodic_memo_recovery` re-runs `extracting` memos after 5 min (the transcript is already saved) |
| Periodic loops | `main.startup_event`: memo recovery + report ticks, Hoy confirm writes, CRM stale gauge, intelligence worker, call reconciler | nothing (they restart) | They also run in every API replica |

`git grep` counts 48 `create_task`/`_spawn` call sites in `backend/app`. This spec covers the first three rows and the periodic loops. The rest move one by one, using the same mechanism.

### 1.1 Gaps in the current call path (verified in `origin/main`)

1. `process_call_recording` returns early when `recording_path` is set ("redelivery"). It sets `recording_path` and `status='recorded'` **before** it creates the memo. A crash between those two steps leaves a call that the reconciler skips (it only looks at `status='dialing'` with `recording_path IS NULL`), and a retry also does nothing. The memo is lost and nothing will ever retry it.
2. `log_call_engagement` saves `hubspot_engagement_id` only after HubSpot answers. A crash between those two steps creates a duplicate HubSpot call on retry.
3. Twilio's `/recording` callback retries now (`#rc=5&rp=ct,rt,5xx`). But the endpoint answers 204 before any durable write, so Twilio's retries can never help once the 204 has gone out.

A job queue solves none of these by itself. The handlers must be made idempotent at every step (§5), whichever option is chosen.

---

## 2. Constraints (verified 2026-10-14)

- **Database access is only through Supabase's REST API.** That means supabase-py, which is synchronous: PostgREST for tables and RPC, plus Storage. `backend/requirements.txt` has no asyncpg, psycopg or SQLAlchemy. `app/config.py` and the local `backend/.env` have no Postgres DSN, only `SUPABASE_URL` and keys.
- **Each PostgREST request is its own transaction.** Two `.execute()` calls are never atomic together. One RPC call (a SQL function) is one transaction.
- **Staging and production share one Supabase project.** They also share one Twilio TwiML app, whose webhooks point at prod (memory `project-staging-calls-hit-prod`, verified 2026-10-09; re-check before Phase 1). Consequences:
  - any migration lands in both environments at once;
  - a staging worker must never claim a prod job;
  - a staging Twilio call is processed by prod.
- **There is a working precedent in prod.** `memo_jobs` + `claim_memo_job(p_kind, p_lease_seconds)` + `publish_memo_job(job, run, result)` (migration `039_memo_intelligence_jobs.sql`) already provide `FOR UPDATE SKIP LOCKED`, a lease and run-id fencing over PostgREST. `services/intelligence/worker.py` drives them from a loop in the API process, with every blocking stage in `asyncio.to_thread`.
- **Linters do not catch the blocking pattern.** `ruff check --select ASYNC` passes on the code that froze prod. `tests/test_no_new_blocking_db_calls.py` covers `app/api/*` routes only, not `services/*`. `call_processor.py` and `log_call_engagement` still run sync `.execute()` on the loop. Moving them into a worker contains the damage: a blocked worker loop delays jobs, not user requests.
- **Railway**:
  - `backend/railway.json` starts `uvicorn app.main:app`;
  - `backend/railway.live.json` starts `uvicorn app.live_main:app` from the same code: one image, a second start command;
  - Railway has no outbound IPv6 (Railway staff on station.railway.com), and Supabase's direct DB host is IPv6-only unless the IPv4 add-on is bought. Any Postgres connection from Railway must use Supavisor's **session pooler** (port 5432, IPv4) or that add-on.

---

## 3. Options

Both options need the same handler work (§5) and the same Railway service (§7). They differ in how jobs are stored, claimed and enqueued.

### (a) DBOS Transact on Supabase Postgres

SignalCore's setup (`OmnistGroup/signalcore`, branch `staging`):
- `dbos>=3.2`;
- workflows are enqueued inside the caller's SQLAlchemy transaction (`packages/db/src/signalcore_db/workflows.py`, `DBOSClient.enqueue_in_transaction`);
- one worker app runs DBOS queues plus plain claim-and-do loops (`apps/worker/src/signalcore_worker/main.py`);
- `recovery.py` lets workers take over each other's unfinished workflows.

SignalCore runs on Cloud SQL through the Cloud SQL connector, not Supabase. Its engine does support a Supavisor transaction-pooler mode, but only for its own asyncpg engine.

What it would cost Vocify:

| Cost | Detail |
|---|---|
| New secret and network path | A Postgres DSN on Railway, through the session pooler (direct host is IPv6-only), as user `postgres.<ref>`. Not the transaction pooler (6543): it drops session features and prepared statements, and DBOS listens with `LISTEN/NOTIFY` by default (`use_listen_notify=True`; it can poll instead). |
| New dependencies | `dbos`, which brings SQLAlchemy and psycopg 3 (DBOS always uses psycopg 3 for Postgres). That is a second data-access stack next to supabase-py. |
| Connection budget | `sys_db_pool_size` defaults to 20 per process, and every session-pooler client holds a real backend. API replicas (if they enqueue) and workers add up against the plan's connection limit, so each one must be sized explicitly. |
| Shared staging/prod DB | DBOS creates and migrates its own `dbos` schema at launch (`run_migrations`). Staging and prod would each need their own `dbos_system_schema` and queue names, and the schema changes on every DBOS upgrade, outside our migration files. |
| The main benefit does not apply | "Enqueue inside the caller's transaction" needs the caller's write on the same connection. Vocify's writes go through PostgREST, which is another connection. Getting atomic enqueue means moving the webhook's writes to psycopg, which is a second way to write `outbound_calls`/`memos` with its own RLS/service-role rules. |
| Workflow rules | Workflow code must be deterministic, and step outputs are serialized checkpoints. Audio bytes cannot be step outputs: the steps would pass storage paths, the same as in (b). |
| Recovery across workers | DBOS recovers by executor id, so a dead replica's workflows need SignalCore-style `recovery.py`, or one fixed executor id with one replica. |

What it gives:
- step-level checkpointing (a crash resumes at the next step, not the job start);
- built-in retries, queue concurrency limits, scheduled workflows and durable sleep;
- a model the team already runs in SignalCore.

### (b) A `jobs` table through PostgREST, claimed by a SQL RPC

This generalizes `memo_jobs`. There is one table, and a few SQL functions called with `supabase.rpc(...)`:
- `FOR UPDATE SKIP LOCKED` picks a row;
- a lease plus a fresh `run_id` fences out a stale worker;
- `available_at` drives backoff and scheduling.

What it would cost:

| Cost | Detail |
|---|---|
| One additive migration | A table and five functions (§4). No new secret, no new dependency, no new network path. |
| No step checkpointing | A multi-step job either re-runs from the top with idempotent steps, or is split into chained jobs (one enqueues the next). §5 does this explicitly for calls. |
| Polling | Workers poll `claim_job` when idle. At 1 s per idle slot, that is a few PostgREST requests a second per replica, on the shared httpx pool from bd0bb04a. |
| Our own small runtime | We write leases, heartbeats, backoff, dead-lettering and graceful shutdown (≈ 200–300 lines plus tests). `services/intelligence/worker.py` already does most of it for one kind. |
| Atomic enqueue only through RPC | Two writes are atomic only inside one SQL function (§6). |

What it gives:
- the same mechanism already in prod (`claim_memo_job`) and the same data path as everything else;
- jobs you can query, replay and alert on with a plain `select`, from the Supabase dashboard and the admin console.

### Rejected

- **Redis queue (arq/RQ/Celery):** new infrastructure, and it cannot enqueue atomically with a Supabase write at all.
- **Supabase Queues (pgmq):** has the same PostgREST-only access as (b), plus an extension to enable on the shared project, and gives nothing (b) lacks at our volume.

### Recommendation: (b)

The gaps in §1.1 are fixed by idempotent handlers plus a durable record that exists before the webhook answers. (b) delivers both:
- with nothing new to operate;
- on a pattern that has already run in prod since migration 039.

DBOS's real advantage, atomic enqueue in the caller's transaction, is out of reach while every write goes through PostgREST. Its other advantage, step checkpointing, is worth less than the cost of a second data-access stack and a session-pooler connection budget for jobs that take minutes, not days.

Revisit DBOS when either of these happens:
- Vocify gets a direct or pooled Postgres connection for another reason;
- Vocify needs long workflows with durable waits (for example multi-day follow-up cadences).

The handler work in §5 carries over to DBOS unchanged.

---

## 4. The `jobs` table and its functions

Data model only; the exact SQL is written in the implementation plan.

```
jobs
  id            uuid pk
  env           text not null            -- settings.ENVIRONMENT: 'production' | 'staging'
  kind          text not null            -- 'call_recording', 'call_memo', 'hubspot_call_log', 'extract_memo', 'cron:…'
  dedupe_key    text not null            -- e.g. 'call_recording:<CallSid>'
  payload       jsonb not null           -- ids and small values only; never audio or transcripts
  status        text not null            -- pending | running | done | dead | cancelled
  attempts      int  not null default 0
  max_attempts  int  not null
  available_at  timestamptz not null default now()
  lease_until   timestamptz
  run_id        uuid
  last_error    text
  created_at, updated_at, finished_at timestamptz
  unique (env, dedupe_key)
  index on (env, kind, available_at) where status in ('pending','running')
```

The functions are all `SECURITY INVOKER`. `EXECUTE` is revoked from `public`, `anon` and `authenticated` and granted to `service_role` only. The table has RLS on and no policies.

| Function | Does |
|---|---|
| `enqueue_job(env, kind, dedupe_key, payload, available_at, max_attempts)` | `insert … on conflict (env, dedupe_key) do nothing`; returns the job id (new or existing). Idempotent, so a webhook retry or a reconciler pass never doubles a job. |
| `claim_job(env, kinds[], lease_seconds)` | Same shape as `claim_memo_job`: pick a `pending` (or lease-expired `running`) row by `available_at` with `SKIP LOCKED`, set `running`, `attempts+1`, new `run_id`, `lease_until`. Returns id, run_id, kind, payload, attempts. |
| `heartbeat_job(id, run_id, lease_seconds)` | Extends the lease only if `run_id` still matches. Returns false when the job was taken over, and the worker then stops it. |
| `complete_job(id, run_id)` | `done` only if `run_id` matches, so a stale run cannot mark someone else's run. |
| `fail_job(id, run_id, error, retry_after_seconds)` | Back to `pending` at `now()+retry_after`, or `dead` when `attempts >= max_attempts`. |

`env` is in the unique key and in every claim, so staging and prod share the table without touching each other's jobs. `memo_jobs` stays as it is. Its revision and supersede rules are specific to intelligence, and its loop simply moves into the worker process (Phase 5).

**Security check before Phase 1:** no migration in the repo enables RLS on `memo_jobs` or revokes `EXECUTE` on `claim_memo_job`/`publish_memo_job`. Supabase grants `EXECUTE` on `public` functions to `anon` by default. Check the live grants. If `anon` can call them, fix it in the same migration.

---

## 5. Which jobs move first, and what each must make idempotent

Order follows the damage done today: lost data first, lost CRM writes second, delay last.

### 5.1 `call_recording` (Phase 3)

- **Enqueued by:** `/webhooks/twilio/recording` and the call reconciler.
- **Dedupe key:** `call_recording:<CallSid>`.
- **Payload:** `call_sid`, `recording_url`, `recording_sid`, `duration`, `started_at`.

Steps, each checking its own output, not a neighbour's:
1. **Store the WAV**, unless `outbound_calls.recording_path` is set. Download from Twilio, upload to Storage, update `outbound_calls`. Twilio keeps recordings until they are deleted, so retries hours later still work.
2. **Make or claim the memo**, unless the call already has `memo_id`:
   - `initiate_vocify_call_memo` + `claim_call_memo`, as today;
   - the `wait_for_live_memo` grace stays;
   - the "recently live" check reads a DB row, not an in-process `live_activity` set, because the worker is another process (see §8, risk 3).
3. **Enqueue the next job** (`call_memo` when the recording made the memo; `hubspot_call_log` when the live transcript made it), then complete.

This replaces the early `return` on `recording_path` (gap 1 in §1.1). The reconciler keeps its job of finding calls whose callbacks never came, but it calls `enqueue_job` instead of `start_recording_job`. The `_settled` cache stops mattering, because enqueueing twice is free.

### 5.2 `call_memo` (Phase 3)

- **Dedupe key:** `call_memo:<memo_id>`.
- **Handler:** `process_vocify_call_background`, but it reads the WAV from Storage by `recording_path` instead of taking `audio_bytes`. Already done when the memo is past `transcribing`.

`RecoveryService` must stop failing `vocify_call` memos stuck in `transcribing` that have a `recording_path`. It enqueues `call_memo` for them instead. This rule exists today regardless of the queue; it is the "Recover stuck call memos" session's scope. Keep that fix compatible with the enqueue.

### 5.3 `hubspot_call_log` (Phase 4)

- **Dedupe key:** `hubspot_call_log:<CallSid>`.
- **Handler:** `log_call_engagement`, or `log_missed_call_activity` for `missed`.

Already done when `outbound_calls.hubspot_engagement_id` is set. To close gap 2, the handler first looks HubSpot up by `hs_call_external_id = CallSid` (it is already set on every call we create, `services/hubspot/call_log.py`). It adopts an existing engagement before it creates one. **To verify in the plan:** that the HubSpot CRM search API filters calls by `hs_call_external_id`.

### 5.4 `extract_memo` (Phase 5)

- **Dedupe key:** `extract_memo:<memo_id>:<pipeline revision>`.
- **Handler:** `extract_memo_async`.

The memo-row pipeline lease (`pipeline_lease.acquire_pipeline_run`) stays as a second guard. Its in-process `_LIVE` dict no longer protects anything across processes; only the DB row does. Today, extraction already survives a restart through the memo-recovery sweep, so this move buys latency (no 5–10 min gap after a deploy) and one place to look. It is last because nothing is lost today.

### 5.5 Periodic loops (Phase 5)

The five loops in `main.startup_event` move to the worker. With N replicas, each tick must run once. Each loop becomes a self-rescheduling job:
- `cron:<name>` with dedupe key `cron:<name>:<tick bucket>`;
- its handler runs the sweep and enqueues the next bucket at `available_at = next tick`.

Whichever replica claims it runs it, and a lost tick is re-claimed when its lease runs out. The API process then starts none of them.

Voice-memo transcription (`process_memo_async`) holds the audio in memory only. It cannot become durable until the audio is stored, which is a separate decision and not in this spec.

---

## 6. Enqueuing atomically from a webhook

There is no shared transaction across PostgREST calls, so the rule is: **a webhook's only durable write is the enqueue, and it answers only after that write committed.**

- `/twilio/recording`:
  - verify the signature;
  - `enqueue_job(…)` (one RPC, run in the threadpool, never on the loop);
  - answer 204;
  - if the RPC raises or times out, answer 503: the callback URL already asks Twilio to retry on 5xx and timeouts (`rp=ct,rt,5xx`, up to 5 times);
  - the reconciler is the backstop past Twilio's retries.
- `/twilio/dial-status` must return TwiML to end the parent leg. It returns `<Response/>` whatever happens, after attempting `enqueue_job('hubspot_call_log', …)`. If that enqueue fails, the reconciler logs the missed call, as it does today.
- When a domain write and its job must commit together (extraction: set the memo `extracting` with its transcript **and** queue the extract), use one SQL function that does both writes. No two-call sequence. Where a two-call sequence is still used, the order is "job first, idempotent": a job that runs before its domain row commits finds nothing to do and is retried by backoff.
- The payload carries ids, never audio or transcripts. Large data stays in Storage and in `memos`.

---

## 7. Railway layout

- **New service `vocify-worker`** in each environment:
  - same repo and root (`backend/`), same Nixpacks image;
  - config file `backend/railway.worker.json`, following `railway.live.json`, with start command `python -m app.worker`;
  - no public domain;
  - restart policy `ON_FAILURE`;
  - variables shared with the API through Railway reference variables, plus `WORKER_KINDS`, `WORKER_CONCURRENCY` and `ENVIRONMENT`.
- **`app/worker.py`:**
  - `K` concurrent slots, default 4;
  - each slot loops: `claim_job` (in a thread) → handler → `complete_job`/`fail_job`;
  - one heartbeat task per running job (lease 120 s, heartbeat every 30 s);
  - idle poll every 1 s, with jitter;
  - blocking Supabase calls in `asyncio.to_thread`, as `services/intelligence/worker.py` does;
  - `loop_monitor` runs here too.
- **Deploys:**
  - on SIGTERM, stop claiming and let in-flight jobs finish within Railway's draining window (`RAILWAY_DEPLOYMENT_DRAINING_SECONDS`; check the default and set it above the longest expected job);
  - anything cut off is re-claimed when its lease expires, within ≈ 2 min;
  - two replicas, or an old and a new deploy overlapping, are safe by construction (`SKIP LOCKED`, `run_id` fencing, idempotent steps). Do not assume exactly one worker.
- **Alerting:**
  - an ERROR log (so Sentry turns it into an issue) for every `dead` job;
  - a 1-minute check in the worker that logs ERROR when the oldest `pending` job of a kind is older than its threshold (`call_recording`: 3 min);
  - with the worker down, nothing processes calls; this alert is how we find out.

---

## 8. Migration safety

- The migration is additive: one new table and five new functions, nothing changed on existing tables. Because staging and prod share the database, it reaches both on apply. Running code ignores it until a flag turns it on. Ship `NNN_jobs.sql` and `NNN_jobs.down.sql` (drop the functions and table), like 063–080.
- Per-kind flags, per environment, read from env vars (`JOBS_CALL_RECORDING`, `JOBS_HUBSPOT_CALL_LOG`, `JOBS_EXTRACT`, `JOBS_CRONS`):
  - **off**: the API runs the kind in-process, exactly as today;
  - **on**: the API only enqueues, and only the worker runs the kind.
  - There is no "both" mode. Rollback is flipping the flag off; jobs already queued are still drained by the worker.
- Risks to plan for:
  1. **Staging cannot exercise the Twilio path on its own.** Staging calls reach prod's webhooks (shared TwiML app). Test Phase 3 on staging by replaying a signed recording callback at the staging API (recipe in memory `project-backend-event-loop-blocking`), or after a staging TwiML app exists.
  2. **A prod-on flag sees staging-made calls too.** Correct, since prod processes them today.
  3. **In-process state the handlers read.** `live_activity.recently_live`, `_recordings_in_flight` and the pipeline lease's `_LIVE` all live in the API process. The worker cannot see them. Each must be backed by a DB row, or dropped where the dedupe key makes it redundant, before its kind moves.
  4. **Worker down = queue grows.** Alert per §7. Twilio recordings and transcripts stay safe in the meantime.

---

## 9. Phased rollout

Every phase is a "big change" under CLAUDE.md: it goes to `staging` first, and to `main` on Dani's OK.

| Phase | Ships | Done when |
|---|---|---|
| 0 — Check | Re-verify §2 (shared Supabase project, no DSN on Railway), live grants on `memo_jobs` functions, Railway draining default, HubSpot search on `hs_call_external_id` | Answers written into the plan |
| 1 — Table | `jobs` migration + down migration, applied in Supabase; grants fixed for `memo_jobs` if needed | `enqueue_job`/`claim_job` work via `supabase.rpc` from a script with the service key; `anon` gets permission denied |
| 2 — Worker | `app/worker.py`, `railway.worker.json`, a `noop` kind; `vocify-worker` service on staging, then prod | Tests: two workers never run one job; an expired lease is re-claimed; `complete_job` with a stale `run_id` is rejected; SIGTERM drains. On staging, a kill mid-job is retried |
| 3 — Calls | `call_recording` + `call_memo` handlers (§5.1–5.2), webhook enqueue + 503 (§6), reconciler enqueues, `RecoveryService` enqueues `call_memo`; flag `JOBS_CALL_RECORDING` | On staging (replayed callback): memo made; worker killed between WAV stored and memo made → memo still made; webhook redelivered 3× → one job, one memo. Then prod flag on |
| 4 — HubSpot | `hubspot_call_log` (§5.3) for answered and missed calls; flag `JOBS_HUBSPOT_CALL_LOG` | Worker killed after HubSpot create, before save → one HubSpot call, adopted on retry |
| 5 — Extraction + crons | `extract_memo` via one enqueue RPC; the five periodic loops and the intelligence loop move to the worker; flags `JOBS_EXTRACT`, `JOBS_CRONS` | API process starts no background loops; a deploy mid-extraction resumes without the 5-min recovery gap |
| 6 — Remove | Delete the in-process paths for moved kinds, once each flag has been on in prod for a week with no `dead` jobs; extend the guard test so `app/api` cannot `create_task` a moved kind | One way to run each kind |

Also outside this spec, but it should happen next: replay the 10 Oct 7–8 calls whose Twilio recordings were never processed (needs Dani's OK). Once Phase 3 is live, the replay is just ten `enqueue_job` calls.

---

## 10. Open decisions for Dani

1. **(b) over DBOS**, per §3. Agree?
2. **Worker down = calls wait** (no in-process fallback when a flag is on). The alternative, falling back to in-process when the enqueue fails, brings back the restart loss this removes.
3. **The alert threshold** for a waiting `call_recording` job (proposed: 3 min) and where it goes (Sentry via ERROR log, as the CRM stale gauge does).
4. **A staging TwiML app**, so Phase 3 can be tested with real staging calls instead of replayed callbacks.

---

Sources for the external facts:
- [Supabase: connecting to Postgres (pooler modes, IPv4)](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase: session mode moved off port 6543](https://supabase.com/changelog/32755-supabase-connection-pooler-deprecating-session-mode-on-port-6543-on-february-28-2025)
- [Railway station: outbound IPv6](https://station.railway.com/questions/outbound-i-pv6-cac0a5fb)
- [Supabase discussion #43111 (Railway ↔ Supabase)](https://github.com/orgs/supabase/discussions/43111)
- [DBOS Python configuration reference](https://docs.dbos.dev/python/reference/configuration)
