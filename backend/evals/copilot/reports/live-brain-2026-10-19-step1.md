# Live call assistant: order of work 1, short answers in the order said (numbers only), 2026-10-19

14 real calls (customer speech stays out of the repository), 300 end-of-turn readings each run, played through `/copilot/live/points`
on the production model path (direct Together, reasoning off, OpenRouter only as its backup), 3 calls at a time:
`python -m evals.copilot.live_brain_run --production-provider --workers 3`. One run before the change, two after it.

## What changed

- The answer shown on its own is capped in code: whole sentences, at most 2 and at most 20 words; a first sentence that is longer
  alone is cut at its last pause (`answer_cut` counts it). Before, the only cap was 260 characters. The prompt asks for 15 words.
- A point's `ref` is only for the same thing said again: something new they add on the same topic is its own point (prompt).
- The new points of one result are sorted by where they were said (turn, then the quote's place in it).

What already held and was not rebuilt: a turn with nothing to handle returns nothing; each point keeps its source turn ids; the
points of one reading come back in one result; duplicate points 0.

## Before and after

| Measure | Before | After (run 1) | After (run 2) |
|---|---|---|---|
| Points per turn that has something (turns with 1 / 2 / 3+) | 1.04 (65 / 3 / 0) | 1.03 (68 / 2 / 0) | 1.04 (65 / 3 / 0) |
| End-of-turn readings that wrote a point (must not rise) | 68 of 300 | 69 of 300 | 68 of 300 |
| Labelled moments with nothing to handle that got a point (must not rise) | 2/4 | 2/4 | 2/4 |
| Labelled moments to handle that got a point | 11/14 | 11/14 | 10/14 |
| Two things said one after the other (proto t20 + t24), two points | no (t24 merged into t20 as a repeat) | yes | yes |
| Results whose points are not in the order said | 0 | 0 | 0 |
| Answer length, words: p50 / p90 / max | 19 / 26 / 31 | 15 / 19 / 20 | 15 / 18 / 20 |
| Answers over 20 words / over 2 sentences | 25 / 3 of 71 | 0 / 0 of 72 | 0 / 0 of 71 |
| Answers cut in code | – | 11 | 11 |
| Invented facts in points (numbers + judge claims) | 0 + 2 | 0 + 0 | 0 + 2 |
| Invented facts in Ahora and the recap (other producers, not changed) | 0 + 1 | 0 + 5 | 0 + 2 |
| Duplicate points | 0 | 0 | 0 |
| Points latency p90, readings that wrote a point (bar ≤ 1100 ms) | 1246 ms | 974 ms | 1012 ms |
| Points latency p50, readings that wrote a point | 796 ms | 784 ms | 704 ms |
| Reading errors | 0 | 0 | 0 |

Labels are the 18 in `labels.json`, proposed by Claude and not confirmed by Dani. "Has something" is the brain's own decision (a point
was written for that turn). "Results not in order" is measured with the same locator the code sorts by. The judge (Sonnet) varies
between runs on the same lines; invented facts in points are not at 0 (the gate is still open, as before the change).
