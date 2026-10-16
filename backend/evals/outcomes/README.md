# Success rate: feasibility check

The success rate of a suggested answer is "of the times the rep said it, how many settled the objection or the doubt".
It is computed LATER and apart from the call (never in the post-call process), from the stored live-help log and the call's own
post-call reading. This folder checks that the verdicts can be trusted before the number is shown (flag
`PLAYBOOK_SUCCESS_RATE_ENABLED`).

1. `python -m evals.outcomes.run --email <rep of the company> --limit 20 --out sheet.csv` writes the 20 latest eligible
   suggestions with our verdict (`used`, `resolved`). Read-only.
2. Fill `label_used` (`used | adapted | not_used | unknown`) and `label_resolved` (`resolved | not_resolved | unknown`) by hand.
3. `python -m evals.outcomes.run --score sheet.csv` prints the agreement and the share of "unknown" and decides:
   `SIGUE` (at least 80% agreement and at most 30% unknown) or `DETENER`.

Until it says `SIGUE`, `PLAYBOOK_SUCCESS_RATE_ENABLED` stays off: the improvements screen still shows coverage and the
cases that need an answer, but no success rate.
