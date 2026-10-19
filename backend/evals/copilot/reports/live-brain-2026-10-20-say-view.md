# Live call assistant: the brain for the "Qué decir" view (numbers only), 2026-10-20

What the build contract (`docs/superpowers/specs/2026-10-20-live-say-view-build-contract.md` §2) asks of the backend, measured
on the same 14 real calls as step 1 (customer speech stays out of the repository), on the production model path: direct
Together, reasoning off, OpenRouter only as its backup; 3 calls at a time. Each run plays every call through
`/copilot/live/points` and `/live/progress` as the dashboard asks them, with the dashboard's own state code
(`shared/live-call/state.js`), and adds per call: Responder taps a quarter, half and three quarters in; a rewrite of the
first 4 points (a third version for 2 of them); a step question for 2 pending items at half way and at the end.

```
cd backend && PATH=$HOME/.railway/bin:$PATH python -m evals.copilot.live_brain_run --production-provider --workers 3
python -m evals.copilot.live_brain_run --production-provider --workers 3 --no-say-view --no-judge   # the tabs view, for latency
```

## What was built

- `LiveReading`: reasons `rewrite` and `ask_step`, `target {point_id, kind, id, version}`, `say_view`. `PointIn` gains
  `source_id` and `versions`; `ProgressIn` gains `parts` (heard so far).
- **Go deeper** (`say_view` only, and only with playbook steps): a point `kind: "deepen"`, its question in `answer`, its
  step in `source`, no decision. Checked in code: it serves a step of this playbook; one open at a time and one per
  reading; never on a sentence that already gives a figure; never when the rep's line after it is a question; never a
  variation of an earlier one; the question must take up a word they said (the spec's "in the prospect's words").
- **Responder with nothing** (no new point and none brought back): `next {kind, id, label, question}`, the item the
  progress reading picked first, else the playbook's order; the playbook's own question when the model wrote none.
- **Rewrite**: `rewrite {point_id, version, answer}` from the same source only, never the same as a shown version, a
  question back for a point not in the knowledge; null when there is no other honest angle.
- **ask_step**: `step_question {kind, id, question}` from the last minutes of the call, the first missing part first.
- **Parts of a step**: generated with the aids once per published version, only in the criterion's own words;
  progress returns `steps[]` with `parts` and `need` (`status: "open"` until `need` parts are heard with their words).
- `POST /live/events` (204, at most 50, written after the response) and migration 086 (`kind = 'ui'`).

## Runs

Run 1 had go deeper and the rewrites as first written; run 2 after the fixes below; run 3 after the last fixes (the code
that lands). "Off" is the tabs view (no go deeper, the same rewrites and step questions) run right after run 1, to tell the
provider's day from the prompt: no judge in that run.

| Measure | Run 1 | Off | Run 2 | Run 3 (lands) | Bar |
|---|---|---|---|---|---|
| Points latency p90, readings that wrote a point | 1486 ms | 1302 ms | 887 ms | 1178 ms | ≤ 1100 ms |
| Points latency p50, readings that wrote a point | 878 ms | 811 ms | 650 ms | 794 ms | |
| Points latency p90, every reading | 1239 ms | 943 ms | 748 ms | 941 ms | |
| Progress latency p90 | 1274 ms | 1089 ms | 921 ms | 1032 ms | ≤ 3000 ms |
| Go deeper written (in 300 end-of-turn readings) | 3 | – | 1 | 1 | does not fire on ordinary sentences |
| Go deeper the judge calls an ordinary sentence | 1 | – | 1 | 0 | 0 |
| Go deeper dropped by the checks in code | – | – | not their words 1 | not their words 3, figure given 1, rep following 1 | |
| Responder with nothing to answer → next written | – (no taps yet) | – | 11 / 28 (17 were points brought back, counted wrongly) | 5 / 6 | |
| Rewrites written (of tried) | 73 / 74 | 72 / 72 | 78 / 79 | 74 / 76 | |
| Rewrite latency p50 / p90 | 483 / 732 ms | 449 / 689 ms | 407 / 464 ms | 433 / 612 ms | reported |
| Step questions written (of tried) | 56 / 56 | 56 / 56 | 56 / 56 | 56 / 56 | |
| Step question latency p50 / p90 | 462 / 1184 ms | 424 / 561 ms | 412 / 489 ms | 406 / 587 ms | p90 ≤ 1100 ms |
| Invented facts in the new lines (rewrite, step question, next): lines flagged | 4 (rewrite) | not judged | 2 (step question) | 0 | 0 |
| Invented facts in the other producers' lines (points, Ahora, recap) | 3 + 1 | not judged | 3 + 1 + 3 | 1 number + 4 + 1 + 1 | 0 |
| Duplicate points | 0 | 1 | 1 | 0 | 0 |
| End-of-turn readings that wrote a point | 76 | 69 | 70 | 81 | |
| Reading errors | 0 | 0 | 0 | 0 | 0 |
| Readings written by OpenRouter (the backup) | 15 | 10 | 2 | 0 | |

Go deeper per call, run 3: 512ea713 1 (turn t38, step `preguntar_tiempo_y_proceso`, judged worth it, and the rep asked
it); every other call 0. Run 2: 916d1bd8 t54 (judged ordinary: feedback about the demo's slowness). Run 1: 512ea713 t38,
aafe089b t13 (both worth it), proto t58 (ordinary: small talk, the question did not take up their words). Each one with the
turn's words is in the details report (`--details`, kept out of the repository).

Parts: 9 of the 14 calls' playbooks have a step whose criterion lists parts (`cualificar_el_encaje` in 8, "al menos tres de
estos datos"; `datos_de_la_empresa` in 1). Done by its parts with the prospect's words: 1 call per run (512ea713 in run 1,
0a187842 in runs 2 and 3); parts heard and not yet enough in 512ea713 (2 in runs 2 and off).

## Fixes between the runs (each from what a run showed)

- Rewrites presumed what the call never showed ("el mes de prueba", "el criterio de éxito que acordamos", "qué te hizo
  cambiar de CRM"): the rewrite, step question and next prompts forbid presuming an agreement, a pilot, a change of tool,
  their CRM or figures. Rewrite inventions 4 → 0; step questions 2 → 0.
- A go-deeper question that did not take up anything they said (small talk), and one on feedback about our demo: the code
  check "takes up a word they said", and the prompt rules out feedback about our product, the demo or the call.
- `next` was dropped when Responder brought an earlier point back into view (that is the answer to Responder): `next` now
  only when nothing at all comes back.
- The steps block for go deeper is one short line per step (no examples): it was the measured +70 ms p50 / +180 ms p90.

## Not met

- **Points latency p90 ≤ 1100 ms**: met in run 2 (887 ms), not in runs 1 and 3 (1486, 1178 ms); the tabs view was 1302 ms
  on the same afternoon and step 1 measured 974 / 1012 ms the day before. It moves with the provider by more than the say
  view's prompt adds. Not met reliably.
- **Invented facts 0**: not met, in the producers this build did not change (points, Ahora, recap: the same kinds as step 1,
  including "Vocify no llama" and a named co-founder). The new outputs had 0 in run 3.
- Go deeper fired once in 300 readings in run 3: it does not fire on ordinary sentences in this sample, and it is rare.
  Whether it is too rare is for Dani to judge on calls.
- Labels are still the 18 proposed by Claude, unconfirmed.
