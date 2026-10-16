# Live call assistant: eval report, 2026-10-16 (numbers only)

Real calls (14 desktop recordings from two companies' reps, sides known from the audio channels; customer speech stays out of the repository), played through
`/copilot/live/points`, `/progress` and `/recap` on the production model path (direct Together, reasoning off; OpenRouter only as its backup:
13 of 886 readings in the full run). Run with `python -m evals.copilot.live_brain_run --production-provider`.

## Status against the spec's gates

| Gate | Status |
|---|---|
| Invented facts 0 | **Not met on the full set** (13 judge claims in 235 lines, before the last guards). The last serial runs (6 calls, 120 lines) had 2 and 0: a competitor claim and an Ahora line adapted from a step example. Not proven at 0; the judge is strict and noisy |
| Duplicate points 0 | **Met**: 0 pairs in every run |
| Decisions vs Dani's labels | **Not measurable yet**: 18 labels exist, all proposed by Claude and none confirmed by Dani; 9/18 agree in the full run (5/9 and 7/15 in the later subsets) |
| Latency, points | **Not met**: readings that wrote a point took p50 0.8 s, p90 1.2–1.6 s serial (bar ≤ 1.1 s; today's card: p50 0.65, p90 1.09). Readings with no point: p50 0.5 s |
| Latency, progress | **Met**: p90 1.2–1.4 s (bar ≤ 3 s) |
| Reading errors 0 | **Met** |

## Full set: 14 calls, 3 at a time (before the "rep already answered" guard and the shorter output caps)

## Gates

| Gate | Result | Bar |
|---|---|---|
| Invented facts | 0 numbers + 13 judge claims in 235 lines | 0 |
| Duplicate points | 0 pairs | 0 |
| Decisions vs labels | 9/18 agree (0/0 on labels a person confirmed) | agree with Dani's labels |
| Points latency, model time, readings that wrote a point | p90 1187 ms | ≤ 1100 ms |
| Progress latency, model time | p90 1215 ms | ≤ 3000 ms |
| Reading errors | 0 | 0 |

## Latency (ms, model time from the request to the end of the model's answer)

| Reading | n | p50 | p90 | max |
|---|---|---|---|---|
| points that wrote a new point | 73 | 835 | 1187 | 1727 |
| points, every reading | 402 | 499 | 931 | 9219 |
| progress | 484 | 775 | 1215 | 8358 |

## What the checks in code dropped or fixed

data_without_evidence: 17, duplicate_became_update: 2, goal_without_evidence: 7, invented_number: 3, step_without_evidence: 74, unanswered_too_soon: 13

## Per call

| Call | Type | Turns | Readings | Points (open / unanswered / promised) | Steps found | Data found | Goal | Provider |
|---|---|---|---|---|---|---|---|---|
| 0a187842 | discovery | 75 | 38 | 2 (0 / 0 / 0) | 3/7 | 2/8 | no | direct 36, openrouter 2 |
| 1778148f | discovery | 72 | 35 | 1 (0 / 0 / 0) | 2/7 | 0/8 | yes | direct 33, openrouter 2 |
| 22ed8182 | negotiation | 57 | 38 | 1 (1 / 0 / 0) | 0/7 | 0/8 | no | direct 37, openrouter 1 |
| 3dd93bcc | closing | 95 | 71 | 2 (0 / 1 / 0) | 0/7 | 0/8 | no | direct 70, openrouter 1 |
| 512ea713 | discovery | 93 | 87 | 13 (0 / 2 / 0) | 5/7 | 6/8 | no | direct 86, openrouter 1 |
| 522c321d | closing | 40 | 30 | 2 (0 / 1 / 0) | 0/7 | 0/3 | no | direct 30 |
| 5c013cf3 | discovery | 136 | 62 | 5 (0 / 0 / 0) | 4/7 | 0/8 | yes | direct 62 |
| 72ab5015 | discovery | 67 | 48 | 4 (0 / 2 / 0) | 0/7 | 0/8 | no | direct 48 |
| 916d1bd8 | discovery | 96 | 86 | 13 (1 / 1 / 0) | 1/7 | 2/8 | no | direct 84, openrouter 2 |
| 9d2bd8db | closing | 96 | 83 | 3 (0 / 0 / 0) | 0/7 | 0/8 | no | direct 82, openrouter 1 |
| 9f125ca1 | discovery | 206 | 86 | 7 (0 / 1 / 0) | 3/7 | 0/8 | no | direct 85, openrouter 1 |
| aafe089b | discovery | 94 | 82 | 12 (0 / 0 / 0) | 0/7 | 7/8 | no | direct 82 |
| cdafc249 | closing | 103 | 62 | 4 (0 / 2 / 0) | 0/7 | 1/8 | no | direct 61, openrouter 1 |
| proto | discovery | 92 | 78 | 8 (0 / 0 / 0) | 3/7 | 0/8 | yes | direct 77, openrouter 1 |

## Serial run: 4 calls, one at a time, with the judge (after the guards)

## Gates

| Gate | Result | Bar |
|---|---|---|
| Invented facts | 0 numbers + 2 judge claims in 78 lines (+7 Ahora lines that are a playbook step's own sentence, listed apart) | 0 |
| Duplicate points | 0 pairs | 0 |
| Decisions vs labels | 7/15 agree (0/0 on labels a person confirmed) | agree with Dani's labels |
| Points latency, model time, readings that wrote a point | p90 1230 ms | ≤ 1100 ms |
| Progress latency, model time | p90 1155 ms | ≤ 3000 ms |
| Reading errors | 0 | 0 |

## Latency (ms, model time from the request to the end of the model's answer)

| Reading | n | p50 | p90 | max |
|---|---|---|---|---|
| points that wrote a new point | 33 | 797 | 1230 | 1680 |
| points, every reading | 134 | 565 | 960 | 3210 |
| progress | 168 | 748 | 1155 | 4568 |

## What the checks in code dropped or fixed

data_without_evidence: 5, invented_number: 1, rep_already_answered: 5, step_without_evidence: 13, unanswered_too_soon: 4

