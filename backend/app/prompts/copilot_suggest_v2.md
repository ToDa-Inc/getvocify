PLAYBOOK (the team's approved answers)

{{entries}}

How to use it:
- When the latest turn is an objection whose category has an approved answer above, say_this follows that answer's approach (its idea, its claims, its tone), said for this conversation: tie it to what this prospect told you in the ROLLING TRANSCRIPT, in their words. Add no fact, number, name or promise about the product that the answer or the context does not contain. If the answer assumes a moment this call has not reached (a proposal or a meeting on a first conversation), keep its idea and leave out what does not fit. In meeting mode keep say_this to one sentence of at most 90 characters.
- Then source_id is that answer's id, exactly as listed.
- When the category has no approved answer, still help as you would without a playbook, from what this prospect said (say_this is never empty); source_id is null and evidence_refs is [].
- evidence_refs are verbatim substrings copied from LATEST TURN only, each at least 12 characters long, showing the objection. If you cannot quote the latest turn, set evidence_refs to [].
