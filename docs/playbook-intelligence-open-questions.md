# Playbook adherence and call intelligence: core questions and possible approaches

Date: 2026-09-30
Status: discussion document. Nothing here is built or decided beyond what is marked "Dani's current answer".

## 1. Why this document exists

We want Vocify to judge sales calls against a company's playbook, give reps useful feedback, and tell the Head of Sales (HoS) where the playbook itself should change. Before building, we tested the current system on real calls. It showed that the problem is harder than "compare transcript to playbook". This document lists what we observed, the questions we must answer, and the approaches available for each.

## 2. What we observed (facts from a test on 30 Sep 2026)

The test used 13 real cold calls from HubSpot (18 Aug to 10 Sep 2026). We scored them in-process against the two playbook versions of the test company. Nothing was written to the database.

**Scoring results**
- Against the published 3-step playbook, every call scored 0/10.
  - Each step packs several requirements into one sentence, for example "ask how much time the team spends logging calls" or "offer a 20-minute meeting with two agenda options".
  - A rep who did most of a step got "missed", because there is no partial credit.
- Against the older 15-step version, scores ranged from 0 to 10, but the high scores were not earned.
  - Headings ("2. Apertura y conversación") and a test value ("asdasd") had been imported as steps.
  - Two short calls got 10/10 from a single matched step. In one of them, the prospect's company was in insolvency proceedings.

**Second test with a plain-language judge (what happened, per step done / partly / not done / not reached, one good, one bad, one fix)**
- The results were more sensible.
- The opening step came out "partly" on all 13 calls. The rep always introduced himself and gave context, but asked "is updating the CRM still a problem for you?" instead of the playbook's exact question.

**Transcript quality**
- The judge rated 5 of 13 transcripts as poor: speaker labels swapped, Spanish and Catalan mixed, garbled phrases.

**Data available today (test company, own data only)**
- 167 call memos from one rep, 5 Aug to 22 Sep 2026.
- `transcript_confidence` is 0.95 on 153 of 167 calls. It does not work as a quality signal today; the cause is not yet traced.
- Since mid-September, calls are recorded as 2 audio channels (rep and prospect separate). The code later re-assigns speakers with a text heuristic and an LLM clean-up, so the channel identity is not kept.
- No word timings are stored for dialer or HubSpot calls.
- "Meeting agreed" is detected on only 3 calls. Most calls were read with an old prompt version.

**Outcomes and feedback**
- Deal won/lost is not stored per call.
- Whether a meeting was actually held is not tracked.
- There is no way for a rep or manager to dispute a verdict.

**Known code issues found while mapping the pipeline**
- The rep/prospect checks expect `You:`/`Them:` labels. Server transcripts use `SPEAKER: S1`, and desktop uses `Tú:`/`Ellos:`. So "the rep said it" silently falls back to "anyone said it".
- Publishing a new playbook version does not re-score anything.
- Insights compare calls to the live version, while each call was scored against its pinned version.
- The playbook structuring prompt in use still writes steps that depend on the prospect's reaction ("the prospect accepts…"). This contradicts the agreed rule that a step is what the rep does.

## 3. What published research and tools say (for context, not as rules)

- **Word-matching vs intent.** Commercial tools (Gong Smart Trackers, Observe.AI) detect the intent behind what the rep says, not exact wording. Exact wording is only enforced for compliance lines.
- **AI-filled scorecards.** Gong's scorecards let AI answer manager-defined questions, with manager override. Gong warns its AI "has a bias to answer 'yes'".
- **Learning from outcomes.** Cresta links behaviours to outcomes across many calls to find what top performers do differently. "Better" is decided statistically, not on one call.
- **Gong cold-call data (100k calls, vendor data, correlation only):**
  - Successful cold calls: the rep talks about 55% of the time.
  - Stating the reason for the call: 2.1x more successful.
  - The number of questions asked made no statistical difference.
  - "Did I catch you at a bad time?" made a booked meeting 40% less likely.
  - This data comes mostly from US calls and may not transfer to Spanish SMB calls.
- **Academic research.**
  - Adaptive selling (adjusting to the customer) is linked to better performance: Franke & Park 2006, a meta-analysis of 155 samples and more than 31,000 salespeople.
  - Effective salespeople have more branched, contingent "scripts", not rigid ones (script-theory research, 1989).

Sources:
- [Gong AI for scoring](https://help.gong.io/docs/gong-ai-for-scoring)
- [Gong 9 elements of cold calls (PDF)](https://www.gong.io/files/gong-guide-9-secret-elements-of-cold-calls.pdf)
- [Gong trackers](https://help.gong.io/docs/understanding-trackers)
- [Cresta sales behaviors](https://cresta.com/blog/4-sales-behaviors-proven-to-increase-revenue-and-drive-conversions)
- [Observe.AI Auto QA](https://www.observe.ai/post-interaction/auto-qa)
- [Franke & Park 2006](https://journals.sagepub.com/doi/10.1509/jmkr.43.4.693)
- [Leigh & McGraw 1989](https://doi.org/10.1177/002224298905300103)

## 4. Core questions

Each question lists the possible approaches. Where Dani has given an answer in discussion, it is marked. Those answers are open for the partner to challenge.

### Q1. Who is this for?
- A. HoS who wants to know that reps run the process.
- B. Rep who wants to get better.
- C. Owner or HoS who wants to learn what works and change the playbook.
- D. Buyer who needs proof of ROI.

Dani's current answer: HoS and rep.

### Q2. What does the HoS actually do with the information?
- A. 1:1 coaching with call examples.
- B. Fix the playbook when the team keeps missing or ignoring a step.
- C. Performance reviews. This needs a defensible score and falls into EU AI Act high-risk territory.
- D. Onboarding new reps.

Dani's current answer: B, fix the playbook. No per-rep scoring for reviews.

### Q3. How much data will a typical customer have?
This decides whether cross-call learning can be statistical.
- A. 1–3 reps, fewer than 20 conversations a week: statistics never become reliable, so learning is qualitative only.
- B. 4–10 reps, 20–50 conversations a week each: qualitative at first, statistical after roughly 1–2 months per step.
- C. 10–30+ reps: statistics within weeks.

Dani's current answer: B.

### Q4. What counts as "the call worked"?
- A. Meeting agreed on the call: immediate, but includes weak yeses.
- B. Meeting held: lags 1–2 weeks. It could be detected from a later recording or calendar event with the same contact, not from CRM hygiene.
- C. Opportunity created or stage moved: depends on CRM data quality, lags weeks.
- D. A ladder of all of these, with each learning saying which rung it rests on.

Dani's current answer: A, meeting agreed.

Open risk: behaviour and outcome would then come from the same transcript, so one misreading can corrupt both.

### Q5. Any meeting, or a qualified one?
The test company's own playbook goal says a meeting without a clear problem and owner does not prove fit.
- A. Qualified meeting only: meeting plus the goal's conditions.
- B. Any meeting agreed.
- C. Both, reported separately.
- D. Whatever each playbook's goal defines. The AI maps it to measurable events and the manager confirms once.

Dani's current answer: D.

### Q6. What should be fixed first?
- A. Playbook text: imported steps are compound, over-specific, headings or prep tasks.
- B. Judge fairness: right intent in different words counts as missed, and there is no partial credit.
- C. Transcript reliability: speaker identity and quality signal.
- D. Learning what works.

Dani's current answer: A, playbook text.

### Q7. How far may the AI change a playbook?
- A. It proposes each change with the reason, and the HoS accepts or rejects each one. The original text is always kept.
- B. It fixes automatically and shows a diff that can be reverted.
- C. It never changes the text; the judge interprets it internally.
- D. It only warns.

Dani's current answer: A.

### Q8. How does the AI find problems in a playbook?
- A. It reads the text (static check) and also runs a silent preview of the draft against the team's recent calls before publishing, to show steps that are never done, never applicable, or always tripped by one detail.
- B. Text only.
- C. Real calls only.

Dani's current answer: A. It falls back to text-only for customers with no calls yet.

### Q9. How often does the rep get feedback?
- A. Every call.
- B. Only on calls that matter, plus a weekly focus.
- C. A daily digest.
- D. On request.

Dani's current answer: A, every call.

Open risk: at 5–10 conversations a day, unread debriefs mean wasted cost. We have not yet checked the open rate (`brief_seen`).

### Q10. What does each debrief show?
- A. One thing done well and one fix with the playbook phrase. The step checklist is collapsed and opened on demand, and variations are shown neutrally.
- B. The full checklist visible.
- C. The fix only.
- D. Several good points, several bad points and a fix.

Dani's current answer: A.

### Q11. What happens when the transcript is poor?
- A. Judge only the reliable parts. Steps whose evidence falls in poor sections become "unknown", never "missed". Poor calls stay out of the HoS statistics.
- B. No debrief below a quality bar.
- C. Always judge, with a warning.

Dani's current answer: A.

Prerequisite: a real quality measure, which does not exist today.

### Q12. Where may public research influence the system?
- A. Suggestions to the HoS only, cited.
- B. Starting assumptions in the learning maths, overridden as own data grows.
- C. Tips to reps.
- D. Not at all for now.

Dani's current answer: A, B and C.

### Q13. What wins when research and the playbook disagree?
- A. The playbook always wins for the rep. Research reaches the rep only where the playbook is silent. Conflicts go to the HoS as a cited proposal.
- B. Strong research can override the playbook.
- C. Show both to the rep.

Dani's current answer: A.

### Q14. How sure must the system be before proposing a playbook change?
- A. Two labelled tiers:
  - "Pattern": qualitative, from about 10+ calls, with examples, marked as a reading.
  - "Evidence": statistical, past a fixed minimum sample.
  - The HoS always sees the tier and the number of calls.
- B. Statistical only.
- C. Qualitative only.

Dani's current answer: A.

Note: existing internal docs use different minimum samples (5, 10, 30 and 8), and one rule must be chosen.

### Q15. When a rep disputes a verdict, what happens? (open)
- A. It applies immediately, marked "corrected". It feeds calibration and statistics, and the HoS can audit and revert. The gaming risk is low because there is no per-rep review score.
- B. The HoS approves it before it counts anywhere.
- C. It is stored only as a calibration label, and the shown verdict stays.

### Q16. Where does the "truth" come from to measure whether the judge is right? (open to revisit)
- A. A founder-labelled set of about 30 calls, used as a test before every prompt or model change.
- B. Corrections made in the product.
- C. Both.
- D. A second AI cross-checking the first.

Dani's current answer: B. Consequence: accuracy cannot be measured until enough corrections exist. A one-tap "is this right?" on random verdicts was suggested, to avoid only hearing complaints.

### Q17. What happens to old calls when the playbook changes? (not yet discussed)
- A. Old calls keep the version they were judged against. New versions apply only to new calls.
- B. Re-judge history silently against the new version, to compare before and after.
- C. Re-judge and replace the history.

### Q18. How do we know this feature is working, say 3 months after launch? (not yet discussed)
Possible signals:
- debrief open rate;
- dispute rate and how often disputes are right;
- playbook proposals accepted by the HoS;
- trend in the rate of qualified meetings agreed.

### Q19. What cost per call is acceptable? (not yet discussed)
With per-call feedback on every call, each extra LLM pass multiplies cost. The approaches below differ by 1 to 3 LLM passes per call.

### Q20. How do we get outcome data without relying on a messy CRM? (not yet discussed)
Candidates:
- the rep's after-call outcome click (exists, behind a flag);
- the meeting accept flow (exists);
- a later recorded interaction with the same contact;
- calendar events;
- CRM stage history (not stored today).

## 5. Possible system approaches

These are the three architectures discussed. Dani leaned towards B, but that was before deciding to answer the "why" questions first.

### A. One judge prompt per call
A single AI call per conversation returns step verdicts, off-script moves, good and bad points, and quality.
- Pros: fastest to build.
- Cons:
  - Facts and judgments are mixed, so pieces cannot be calibrated separately.
  - A playbook change means re-reading every call.
  - Off-script moves come out as free text, so they cannot be grouped and learned from across calls.

### B. Layered: facts, then judgment, then learning
1. **Signal:** turns with reliable rep/prospect identity (from audio channels), timings, and a quality score per section of the call.
2. **Call map:** a playbook-independent description of the call:
   - each rep move, with its purpose and a quote;
   - the prospect's reactions;
   - how far the call got, and who ended it and why;
   - outcome events.
3. **Playbook alignment:** a cheap pass that compares the call map to a playbook version. Per step: done, partly, not done, not reached or unknown, plus "variation" when a step's purpose was achieved differently. Rep moves that match no step become off-script moves.
4. **Outcomes:** events defined by the playbook goal, some from the call and some later from other sources.
5. **Learning:** deterministic statistics per step and per group of similar off-script moves.
   - Minimum samples and labelled tiers.
   - Controls for how far the call got and for disqualified prospects.
   - Public research used as starting assumptions.
6. **Proposals:** the AI writes playbook-change proposals using only the evidence from step 5. The HoS approves each one.

- Pros:
  - Works for any playbook format, because the call map does not depend on the playbook.
  - A playbook change re-runs only the cheap alignment.
  - Each layer can be tested on its own.
- Cons: two AI passes per call and more engineering.

### C. Embeddings first
Match steps by text similarity and group rep utterances by similarity, then compare against outcomes.
- Pros: cheap and deterministic.
- Cons: similar-sounding text is not the same intent, especially on noisy Spanish/Catalan transcripts. It cannot express "partly", and its explanations are weak.

## 6. Principles already agreed in earlier Vocify design docs (for reference)

- The company's playbook is the yardstick. A step is what the rep does; the prospect's answer is measured separately.
- "Unknown" is never counted as "missed".
- Every claim needs a quote that exists in the transcript.
- Rules compute numbers; the AI only writes the text. No causal claims. No conclusions below a minimum sample.
- No tone or emotion analysis. No rep rankings.

## 7. Suggested next step

Agree on the answers above, especially the open questions Q15–Q20. Then decide which part to design first. Based on the current answers, that would be playbook quality (Q6–Q8), since it helps even before any learning exists.
