# Blind judges

Rubrics for the Sonnet judges that score what the models write, where a regex or a label cannot:

| Rubric | Judges |
|---|---|
| `JUDGE_CRM_AB.md` | step 1, two versions side by side (note, tasks, CRM fields), blind |
| `JUDGE_CRM.md` | step 1, one version against `must_have` / `must_not` |
| `JUDGE_COACH.md` | coaching verdicts per playbook step |
| `JUDGE_BRIEF.md` | the brief for the next call |
| `JUDGE_EMAIL.md` | follow-up email drafts |
| `RUBRIC.md`, `RUBRIC_GENERIC.md`, `RUBRIC_NEXT.md` | how the labels in `evals/C04/real` were written |

The rubrics say the call is at `calls/<memo_id>.txt`: point the judge at
`evals/C04/real/.cache/transcripts/` instead. `evals/tools/ab_judge.py build` exports it there; it is
gitignored because it is customer speech.

## A/B on step 1

1. Run step 1 for each system on the same calls and the same call reading:
   `EXTRACTION_MODEL=<model> .venv/bin/python evals/tools/step1_timed.py evals/C04/notes/broad.json evals/C04/real/.cache/run-<v8 run>.json <dir>`
2. `.venv/bin/python evals/tools/ab_judge.py build <ab_dir> <dir_X>/crm_grounded.json <dir_Y>/crm_grounded.json evals/C04/real/<set>_next.local.json`
3. Two Sonnet judges, one per file (`ab_1.json`, `ab_2.json`), each told to follow `JUDGE_CRM_AB.md`, read
   each transcript before judging the call, add `"better": "A" | "B" | "same"`, and write
   `ab_scores_<n>.json` in input order. They never see which system is which.
4. `.venv/bin/python evals/tools/ab_judge.py unblind <ab_dir>`

## Reference (2026-10-06, 54 calls of broad + vocify)

DeepSeek V4.1 Flash without reasoning on Together, with `GROUNDED_NO_REASONING_RULES`, against Gemini 3.5
Flash-Lite: preferred 42 to 4 (8 the same); wrong or inferred fields 12 vs 42; invented facts in the note
8 vs 18; must_have covered 165 vs 122; fields left empty 34 vs 27; note score 4.22 vs 3.31.
