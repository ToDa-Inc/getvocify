# Memo pipeline integrity: raw transcripts, run identity, single-flight — Design

**Date:** 2026-08-26
**Status:** Plan only. Nothing implemented.
**Surfaces:** `backend/app/api/memos.py`, `backend/app/services/{extraction,extraction_context,transcript_sanitize,pipeline_meta,recovery}.py`, `backend/app/services/hubspot/call_processor.py`, `memos` table

## Why this document exists

Three HubSpot calls were reviewed by hand over five days (Ascale `f785d8e6`, Torrot `8b160a20`, Taptap `be0cb8dd`). Each review produced a different list of per-call defects, and each "fix" was a prompt edit verified by re-running one memo and eyeballing JSON.

That loop does not converge, for reasons that are structural rather than per-call:

- Latency claims could not be substantiated, because `pipeline_meta.total_ms` is a sum of overlapping stages appended across runs.
- Transcript-quality claims could not be attributed to a stage, because the raw provider output is never stored.
- Duplicate work could not be attributed to a trigger, because runs have no identity.

This document records what is provable from the code, names the root causes, and lays out a phased plan. The goal of Phase 0 is not a feature: it is to make the next quality question answerable without hand-reading JSON.

## Evidence

### Taptap memo `be0cb8dd-7ec3-452b-8fcf-d4e7ef351ee1`

`pipeline_meta.stages` contains five `context` + `extract` pairs, all starting within ~900 ms of each other, and no `stt` or `sanitize` stage. `total_ms` reports `56372`; the wall clock between the first and last stage is ~12 s.

**No transcription ran during that request.** `process_hubspot_call_background` wraps STT and cheap sanitize in its own `pipeline_run` and persists them before extraction starts (`backend/app/services/hubspot/call_processor.py:154-174`). Neither stage is present, so the stored transcript is the artifact written on 2026-08-06 (`createdAt`), untouched by 20 days of sanitizer improvements.

**All five runs came from `extract_memo_async`, not the `/re-extract` endpoint.** `extract_memo_async` records a `context` stage (`backend/app/api/memos.py:180`). `re_extract_memo` loads the same context *outside* its `pipeline_run` block and never records that stage (`backend/app/api/memos.py:1722-1726`). Five `context` stages therefore mean five fire-and-forget background tasks.

**Which trigger spawned them is not recoverable from the data.** Stage records carry `name`, `ms`, `at`, `model`, `provider` (`backend/app/services/pipeline_meta.py:97-109`) — no run id, no trigger, no attempt number.

### Torrot memo `8b160a20-232b-459a-86a3-72c868ce3d05`

Wall clock create → `pending_review` was 44 s against a `total_ms` of 17513. An earlier review attributed the difference to a specific ~19 s gap after STT. That attribution was not supportable: with append-only stages, no run boundaries, and unmeasured phases (HubSpot download, field-spec fetch, cheap sanitize, STT language detect), the gap cannot be decomposed. The only defensible statement is that a majority of wall time is spent in phases that emit no stage record.

## Root causes

### RC1 — The transcript is a destructively overwritten single field

There is no `transcript_raw`, `raw_transcript`, or equivalent column anywhere in the backend (grepped). The lifecycle is:

1. Deepgram utterances are formatted to `S1:` / `S2:` lines (`backend/app/services/deepgram_batch.py:52-73`).
2. `sanitize_user_transcript` applies glossary, casing, speaker canonicalization and spelled-email reconstruction, and only the **result** is stored (`backend/app/api/memos.py:246`).
3. Background polish later overwrites the same column again (`backend/app/services/transcript_sanitize.py:963`).

Consequences:

- Improving the sanitizer cannot benefit any existing memo.
- A sanitizer or diarization change cannot be A/B'd or regression-tested — there is no input to replay.
- A bad polish is unrecoverable.
- "The transcript looks bad" cannot be assigned to Deepgram, cheap sanitize, or polish.

For HubSpot calls the audio still lives in HubSpot, so `re-transcribe` is a partial escape hatch. For uploads, WhatsApp, and live sessions the audio is never persisted, so the raw text is gone permanently.

This is the direct cause of the Taptap transcript still showing `S3`, `Boys y Fai`, `Voice HIFI`, and `Toni`.

### RC2 — No pipeline run identity and no single-flight guard

Six call sites spawn pipeline work as detached tasks:

| Site | Trigger |
| --- | --- |
| `backend/app/api/memos.py:260` | `start_extraction_from_transcript` (upload, batch STT, HubSpot call, webhook) |
| `backend/app/api/memos.py:439` | upload path |
| `backend/app/api/memos.py:1628` | `confirm-transcript` |
| `backend/app/api/memos.py:1857` | `re-transcribe` |
| `backend/app/api/crm.py:329` | `POST /hubspot/calls/{id}/process` |
| `backend/app/services/recovery.py:105` | startup / admin / health recovery |

Every guard is a non-atomic read-then-write. `confirm-transcript` reads status, returns early if `extracting`, then updates in a separate statement (`backend/app/api/memos.py:1595-1622`) — the comment says "avoids duplicate work on retry", but concurrent callers all observe the pre-update value and all proceed. `re-transcribe` has the same shape (`backend/app/api/memos.py:1808`).

`merge_pipeline_meta` appends new stages to the existing list and recomputes `total_ms` as the sum of every stage ever recorded (`backend/app/services/pipeline_meta.py:112-127`). `persist_pipeline_meta` is itself a read-modify-write with no optimistic concurrency (`backend/app/services/pipeline_meta.py:152-178`), so concurrent runs can also lose each other's stages.

Local dev runs `uvicorn --reload` (`start.sh:38`) and production runs a single worker (`backend/Procfile`), so this is task-level concurrency, not multi-process.

Consequences: duplicated LLM spend and duplicated HubSpot reads; unattributable duplicates; and no field anywhere that answers "how long did this memo actually take".

### RC3 — The extraction prompt has no temporal anchor

`backend/app/services/extraction.py` never injects the current date or the call date. The prompt instructs `closedate = null unless explicit calendar date` and post-processing scrubs relative phrases (`backend/app/services/extraction.py:829-845`), but nothing supplies a reference point.

`hs_timestamp` is already fetched into `CALL_PROPERTIES` (`backend/app/services/hubspot/calls.py:16-25`) and a parser exists (`parse_hubspot_timestamp_ms`), but `process_hubspot_call_background` reads only the recording URL and duration from `props` and discards the timestamp (`backend/app/services/hubspot/call_processor.py:137-143`).

Observed failures:

- Taptap: "semana del 24" / "el 26" / "jueves" → `nextStepSchedules: ["2026-03-26"]`. March was selected because the 26th is a Thursday in March 2026; the call is from August.
- Torrot: "20 y pico de septiembre" → `nextStepSchedules: ["en un mes"]`, unresolved.

No prompt wording can fix a missing input.

### RC4 — `existing_values` round-trips into proposed writes

Current CRM values are injected as `CURRENT VALUE: …` (`backend/app/services/extraction.py:549`). Deal stage is force-added to the requested fields on every memo regardless of the user's allowlist (`backend/app/api/memos.py:74-76`) with an inference hint (`backend/app/api/memos.py:39-45`).

Both Torrot and Taptap returned `dealstage: "5022848247"` — the record's existing stage id echoed back. There is no post-processing step that drops a proposed value identical to the current value, so an echo is indistinguishable from an intentional write.

### RC5 — Speaker structure is an inferred guess, not a constraint

`canonicalize_rep_prospect_speakers` scores each speaker and returns the input **unchanged** when the best score is below 2 (`backend/app/services/transcript_sanitize.py:289`). `_rep_turn_score` keys off `rep_name` and `seller_company` (`backend/app/services/transcript_sanitize.py:227-263`).

This is circular on exactly the calls that need it: fixing speakers depends on matching "Dani" and "Vocify" in text where ASR wrote "Toni" and "Boys y Fai". It also treats speaker **count** as provider truth — Deepgram returned three speakers on a two-party phone call, and nothing rejects that. The extraction prompt then tells the model `S1 = rep, S2 = prospect, if more than 2 speakers treat S1 as rep and all others as customer side` (`backend/app/services/extraction.py:398-402`), which is a hint, not a normalization.

For a HubSpot 1:1 call the party count is known a priori and should be enforced.

### RC6 — No regression harness

`backend/tests/test_extraction_policy.py` covers policy classification, number grounding, and enum patching, but there is no fixture-driven test that takes a real transcript plus a real field schema and asserts the resulting proposed writes. Every quality judgment so far has been a human reading one memo. Nothing prevents the Ascale enum-filling change from regressing Torrot's correct all-null behaviour.

## Goals

1. Any stored transcript can be re-derived from preserved raw input, for every source, without re-billing STT where avoidable.
2. A single memo has at most one live pipeline run, and every stage is attributable to a run and a trigger.
3. `pipeline_meta` can answer "what was the wall clock of the latest run, and which phase dominated it".
4. Relative dates resolve against the call date.
5. Proposed writes never include an unchanged echo of a current CRM value.
6. HubSpot 1:1 calls are normalized to two speakers before extraction.
7. The three reviewed calls become fixtures, so future changes are checked against them automatically.

## Non-goals

- Changing STT providers, or re-tuning Deepgram parameters beyond what diarization normalization requires.
- Rewriting the extraction prompt's discovery-field semantics (that work landed for Ascale and should be left alone until it is under test).
- A UI for pipeline timings. Phase 0 makes the data correct; visualization is separate.
- Backfilling `transcript_raw` for historical memos where audio is gone. Those stay as-is and are marked.
- Storing audio.

## Approaches considered

### Preserving raw transcripts

**A — Add a `transcript_raw` column, write-once.**
Pros: one migration; replay is a pure function of `transcript_raw` + current sanitizer; no new table. Cons: only one raw version per memo (fine — raw is provider output, and re-transcribe legitimately replaces it).

**B — Version every transcript revision in a new `memo_transcripts` table.**
Pros: full lineage (raw → cheap → polished), supports diffing revisions. Cons: new table, new joins, migration of read paths in dashboard and extension for a benefit that Phase 0 does not need.

**C — Keep overwriting; rely on `re-transcribe` to recover.**
Pros: nothing to build. Cons: does not work for uploads, WhatsApp, or live; re-bills STT; and still cannot A/B a sanitizer change offline.

**Decision: A**, with `transcript_stt_meta` alongside it to record provider, model, language, and the raw speaker count. B remains the natural follow-up if transcript diffing becomes a product surface.

### Single-flight

**A — Postgres advisory lock per memo.**
Pros: strong. Cons: requires a direct connection; the codebase talks to Supabase over REST via `supabase-py`.

**B — Compare-and-swap on the `memos` row plus a `pipeline_run_id` token.**
Pros: works over the REST client — conditional `UPDATE … WHERE id = ? AND pipeline_run_id IS NULL` and inspect the returned rows; the token doubles as the run identity needed for RC2. Cons: a crashed run leaves a stale token, so it needs a lease timestamp and the existing recovery sweep must clear it.

**C — In-process `asyncio.Lock` / task registry keyed by memo id.**
Pros: trivial. Cons: dies on restart, does not survive `--reload`, and would not have prevented the Taptap burst if any of it came from recovery after a restart.

**Decision: B.** `pipeline_run_id` + `pipeline_run_started_at` on `memos`; acquisition is a conditional update whose result set determines whether the caller may proceed. Recovery becomes the lease reaper instead of an unconditional re-queuer.

### Run-scoped timings

**A — Restructure `pipeline_meta` into `{runs: [...]}` and drop the flat `stages` list.**
Cons: breaking. `src/lib/memo-poll.ts:28` and `chrome-extension/lib/review-screen.js:265` both read `stages` to detect a `sanitize` after the latest `extract` (the transcript-polish poll).

**B — Keep `stages` flat, stamp each stage with `run_id`, and add a `runs` index with wall clock.**
Pros: backward compatible with both existing readers; `total_ms` can be redefined as the latest run's wall clock while the raw sum stays available. Cons: slight redundancy.

**Decision: B.**

### Diarization

**A — Hard two-party collapse for `hubspot_call` sources.** Any speaker beyond the two most-spoken folds into the prospect side; the existing scored heuristic decides only *orientation* (which of the two is the rep), and if scoring is inconclusive, orientation falls back to the current behaviour rather than leaving three speakers.

**B — Ask Deepgram for a speaker cap.** Not available for `diarize` on Nova-3 in the current query shape (`backend/app/services/deepgram_batch.py:36` already documents that `diarize_model` 400s alongside `diarize`).

**C — Second LLM pass purely for speaker attribution.** Higher cost and latency; the polish pass already attempts turn repair and its output is frequently rejected by the length guard (`accept_llm_sanitize`, `backend/app/services/transcript_sanitize.py:669-683`).

**Decision: A**, with the party count taken from the call's known participant structure, not from the provider.

## Architecture

### Schema (migration `024_memos_pipeline_runs.sql`)

```sql
ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS transcript_raw TEXT,
  ADD COLUMN IF NOT EXISTS transcript_stt_meta JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS pipeline_run_id UUID,
  ADD COLUMN IF NOT EXISTS pipeline_run_started_at TIMESTAMPTZ;
```

- `transcript_raw` — verbatim provider output, written once per transcription. `re-transcribe` replaces it; sanitize and polish never touch it.
- `transcript_stt_meta` — `{provider, model, language, raw_speaker_count, diarized}`.
- `pipeline_run_id` — non-null means a run holds the lease. Cleared on completion and on failure.
- `pipeline_run_started_at` — lease timestamp for reaping.

### `pipeline_meta` shape

```jsonc
{
  "runs": [
    {
      "run_id": "…",
      "trigger": "re_transcribe | confirm_transcript | recovery | hubspot_process | upload | re_extract | webhook",
      "started_at": "…",
      "ended_at": "…",
      "wall_ms": 24180,
      "outcome": "ok | failed"
    }
  ],
  "latest_run_id": "…",
  "stages": [ { "run_id": "…", "name": "stt", "ms": 7958, "at": "…" } ],
  "total_ms": 24180
}
```

`total_ms` becomes the latest run's `wall_ms`. `stages` stays flat and append-only so existing readers keep working.

### Run lifecycle

```
acquire_pipeline_run(memo_id, trigger)
  → conditional UPDATE … SET pipeline_run_id = :new, pipeline_run_started_at = now()
      WHERE id = :memo_id AND (pipeline_run_id IS NULL OR pipeline_run_started_at < now() - lease)
  → returns run_id, or None if another run holds the lease
```

Every spawn site calls this **before** `create_task` and skips silently when it returns `None`. Release happens in a `finally`, alongside `persist_pipeline_meta`.

### Phases to instrument

Currently unmeasured and each getting a stage: `download` (HubSpot recording fetch), `field_specs` (CRM schema for the allowlist), `stt_lang_detect`, `sanitize_cheap`. Existing stages keep their names.

### Call-date propagation

`process_hubspot_call_background` parses `hs_timestamp` and passes it into `start_extraction_from_transcript`, which stores it and forwards it to `ExtractionService.extract` as `call_date`. The prompt gains a dated header, and a post-processor resolves `nextStepSchedules` entries such as "semana del 24" or "en un mes" against `call_date` rather than leaving the model to guess a month.

## Phased plan

### Phase 0 — Substrate (blocking; nothing else is measurable without it)

**File map**

Create:
- `backend/migrations/024_memos_pipeline_runs.sql`
- `backend/app/services/pipeline_lease.py` — `acquire_pipeline_run`, `release_pipeline_run`, `reap_expired_leases`
- `backend/tests/test_pipeline_lease.py`
- `backend/tests/test_pipeline_meta_runs.py`

Modify:
- `backend/app/services/pipeline_meta.py` — `run_id` on stages, `runs` index, `total_ms` = latest wall clock
- `backend/app/services/hubspot/call_processor.py` — store `transcript_raw` + `transcript_stt_meta`; `download` stage
- `backend/app/api/memos.py` — lease at all spawn sites; `field_specs` and `sanitize_cheap` stages; never overwrite `transcript_raw`
- `backend/app/services/transcript_sanitize.py` — polish writes `transcript` only
- `backend/app/services/stt_batch.py` — `stt_lang_detect` stage
- `backend/app/services/recovery.py` — reap leases instead of unconditionally re-queuing
- `docs/DATABASE_SCHEMA.md`

**Tasks**

- [ ] Migration 024 and schema doc update.
- [ ] `pipeline_lease.py` with tests for: acquire on idle memo, refuse on held lease, acquire on expired lease, release clears the token.
- [ ] `pipeline_meta` run scoping, with a test asserting `total_ms` equals the latest run's wall clock when two runs are recorded.
- [ ] Wire the lease into all six spawn sites; each records its `trigger`.
- [ ] Persist `transcript_raw` on every transcription path; assert sanitize and polish leave it untouched.
- [ ] Add the four missing stages.
- [ ] Recovery reaps expired leases; add a test that a memo with a live lease is not re-queued.

**Verification:** `cd backend && python -m pytest tests/test_pipeline_lease.py tests/test_pipeline_meta_runs.py -v`, then re-transcribe one HubSpot call and confirm `pipeline_meta.runs` has exactly one entry whose `wall_ms` is within ~1 s of observed request-to-`pending_review` time.

### Phase 1 — Correctness of inputs

**File map**

Create:
- `backend/app/services/relative_dates.py` — resolve Spanish/English relative phrases against a reference date
- `backend/tests/test_relative_dates.py`
- `backend/tests/test_speaker_normalization.py`

Modify:
- `backend/app/services/hubspot/call_processor.py` — parse and forward `hs_timestamp`
- `backend/app/api/memos.py` — thread `call_date`
- `backend/app/services/extraction.py` — dated prompt header; resolve `nextStepSchedules`; drop proposed values equal to current
- `backend/app/services/transcript_sanitize.py` — two-party collapse for call sources

**Tasks**

- [ ] `relative_dates` covering "semana del 24", "el 26", "en un mes", "20 y pico de septiembre", "martes que viene" → resolved ISO or `None`, anchored on a supplied reference date. Weekday claims must never override an explicit day-of-month.
- [ ] Thread `call_date` from `hs_timestamp` through to the prompt; fall back to `created_at`.
- [ ] Post-process `nextStepSchedules` through the resolver.
- [ ] Drop any proposed field whose value equals the injected `CURRENT VALUE` (fixes the `dealstage` echo without removing stage inference).
- [ ] Two-party collapse: fold speakers beyond the top two into the prospect side for `hubspot_call`; keep the scored heuristic for orientation only.

**Verification:** `python -m pytest tests/test_relative_dates.py tests/test_speaker_normalization.py -v`. Then re-extract Taptap and assert `nextStepSchedules` is `2026-08-26`, `dealstage` is absent from proposed writes, and the extraction input has two speakers.

### Phase 2 — Regression harness

**File map**

Create:
- `backend/tests/fixtures/calls/ascale_f785d8e6.json`
- `backend/tests/fixtures/calls/torrot_8b160a20.json`
- `backend/tests/fixtures/calls/taptap_be0cb8dd.json`
- `backend/tests/test_extraction_fixtures.py`
- `backend/scripts/eval_calls.py` — opt-in live LLM eval

**Tasks**

- [ ] Each fixture holds `transcript_raw`, field specs, `existing_values`, `call_date`, and expected post-processor outcomes.
- [ ] Fixture tests exercise prompt construction, `apply_fill_policies`, `drop_unspoken_numbers`, `pending_enumeration_specs`, current-value drop, and date resolution — no network.
- [ ] Assert the behaviours each review established: Ascale fills `partner_channel` / `influencer` / `influencer_with_path`; Torrot stays all-null with a resolved September date; Taptap resolves August, writes no `unknown`, and does not disqualify a booked meeting.
- [ ] `eval_calls.py` runs the real model against the fixtures and prints a field-level diff, gated behind an env var.

**Verification:** `python -m pytest tests/test_extraction_fixtures.py -v`.

## Open questions

1. **Lease duration.** Recovery currently treats 5 minutes as stuck (`backend/app/services/recovery.py:21`). A long HubSpot recording plus STT can legitimately exceed that. Proposal: lease of 10 minutes, and recovery only reaps beyond it.
2. **Backfill.** `transcript_raw` will be null for every existing memo. Proposal: leave null and treat null as "raw unavailable"; for HubSpot-sourced memos, `re-transcribe` populates it on demand.
3. **`dealstage` force-add.** `_curated_field_specs_for_primary_crm` appends the stage field on every memo even when the user did not enable it (`backend/app/api/memos.py:74-76`). Once the current-value echo is dropped this becomes harmless, but it is worth confirming that inferring stage on every call is still wanted.
4. **Polish rejection rate.** `accept_llm_sanitize` rejected the Torrot polish. With `transcript_raw` stored we can measure the rejection rate offline before deciding whether to loosen the guard or drop the pass.

## What this explicitly does not fix

Ordering matters here. Phase 0 delivers no visible product improvement — it makes the system measurable and idempotent. The per-call defects catalogued in the three reviews are addressed in Phase 1, and only Phase 2 stops them from silently returning. Attempting Phase 1 first repeats the loop that produced this document: a prompt edit, one memo re-run, and no way to know what else moved.
