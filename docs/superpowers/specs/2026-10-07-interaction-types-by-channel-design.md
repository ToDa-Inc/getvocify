# Interaction types by channel — design

Date: 2026-10-07, updated 2026-10-08 · Base: `origin/staging` (8362ce8f; local `staging` is 33 commits behind)

## Intent (Dani, 2026-10-06/07)

Every recording carries two labels: the **channel** (fixed, automatic) and the **type** (the
company's own list, configurable). Setting types up and detecting them must be as easy as possible.
The type of an interaction is not tied to the member's sales role: a member who records a call
gets call types, the same member recording a meeting gets meeting types.

## Decisions (answered by Dani)

- D1. Channel = call or meeting, from the source (desktop `CallSource.swift`: Meet/Zoom/Teams →
  meeting; HubSpot calling/Aircall/Ringover/Dialpad/JustCall/WhatsApp → call). **Visit is hidden for now.**
- D2. Type is not related to role. Detection never reads `sales_role`.
- D3. **A type does not need a playbook.** A type with no published playbook is still detected,
  shown and filterable; it is only not scored and gets no live help.
- D4. **No conversion of existing types.** What a type stores today stays as it is.
- D5. **No role on types at all** (2026-10-08). Settings never asks for one, a custom type needs no
  rule, and nothing about a type depends on a playbook.
- D6. **The island lets the rep set the channel, subtly.** The channel comes from the origin of the
  recording (HubSpot calling → call, Meet → meeting); the rep can switch it in one tap. The type is
  then proposed for that exact channel, from the conversation.
- D7. **Live type = suggestion, post-call reading = the assessment.** The live type only picks the
  playbook for live help; the call reading after the call decides, and the island's post-call card
  shows that answer with one-tap change.

## How it works today (for reference)

- Channel: `interaction_kind` (call | meeting | visit | voice_note), stamped at capture, derived by
  origin for old rows (`captures.interaction_kind_for`).
- Type: `memos.sales_motion_key`, decided in up to three moments:
  1. At capture: role default (SDR → discovery, AE → closing; else call → discovery, meeting → closing)
     or a company rule (`applies_to`: role, channels, contact, deal stages). Behind
     `SALES_ROLES_ENABLED` + `PLAYBOOK_ROUTING_ENABLED`.
  2. Live on the desktop: free guess (last type with the contact, else the rule), then one
     `COPILOT_MODEL` proposal at ~70 words and a second one at ~200 if unsure. Rep pick wins.
  3. After the call: the call reading names the type in the same pass
     (`INTELLIGENCE_CALL_READING_ENABLED`). Never moves a manual pin.
- Only types with a **published** playbook can be candidates or pinned (`live_version_id` gate in
  `apply_reading_type`, `_pin_picked_type`, `call_type.published_types`).
- Jev does not detect the type. Live it runs the turn check (finished? objection kind?); after the
  call it classifies meeting agreed / pain / objection kind and detects the STT language.

### Defects found

- **B1. The desktop saves Vocify's live guess as a rep pick.** `DesktopMeetingProvider.tsx:309`
  copies whatever the chip shows into `draft.type`; both send paths pass it on (meeting `:353`,
  island call `:796`); `memos.py:1070` pins it as `manual` (`picked: "during_call"`). The call reading can then never correct a type guessed from ~70 words.
- **B2. Candidates are not filtered by channel.** The live proposal and the call reading choose from
  every published type, so a cold call can be tagged Closing.
- **B3. Custom types are described to the call reading by name only**
  (`type_classifier.describe_type`: "{label}: a call type defined by this company."), while the live
  proposal sees the playbook steps. Two deciders, two different inputs.

## Design

### Storage (no data conversion)

- A type is what already exists: an `interaction_types` row and/or a `playbooks` row (label,
  `applies_to`). A `playbooks` row with no version is already listed as `missing` by
  `list_playbook_motions`, so a type without a playbook needs no new table.
- **Channel of a type = `applies_to.channels`.** Empty or absent = both channels. Catalog types keep
  their effective defaults (discovery, inbound → call; closing → meeting; ae_discovery,
  negotiation → call and meeting). `visit` in stored channels is kept and ignored while visits are hidden.
- `applies_to.role` stays stored and is **ignored everywhere types are concerned** (D2, D4, D5):
  detection, the type list and the add-type form. Custom types no longer need a rule (`rule_required` goes).
- New: `playbooks.recognize TEXT` — one sentence, "how to recognise this type". Optional. Migration **076** (075 is `075_crm_call_recordings`, already on `origin/staging`).
  (`applies_to` validation rejects extra keys, so it cannot live there.)
- Memo pin: `sales_motion_key` = the type, always. `playbook_version_id` = the live version when the
  type has one, else NULL. Scoring, coaching and live help already need a version; NULL skips them.

### Detection

Candidates = the company's non-deleted types whose channels include the recording's channel,
with or without a playbook, plus `internal`.

1. **At capture.** One candidate → pin it, no AI. Several → a company rule with a CRM condition
   (new / existing / inbound contact, deal stage) may decide; else the memo starts with no type.
   No role default.
2. **Live (desktop).** Same as today (history guess, proposal at ~70/~200 words, rep pick final),
   but only over the channel's candidates. The draft records **who** chose:
   `typeSource: "rep" | "vocify"`. Only `rep` is pinned `manual` (fixes B1); a Vocify guess is pinned
   `live` and stays correctable.
3. **After the call.** The call reading picks among the channel's candidates and is the final answer
   unless the pin is `manual` or a decided company rule. A single-candidate pin is not re-read.
4. **Retag.** One click on the island post-call card and in Interacciones; always `manual`.

Both AI deciders get each candidate from one shared describer: name + `recognize` + playbook
steps when there is a published playbook (fixes B3).

Pin precedence: `manual` > company rule (decided) > call reading > `live` > history > single candidate.

### Island (desktop)

During the call the island shows one quiet line: **channel · type**, e.g. `Llamada · Cold call ✨`.

- **Channel** is pre-set from the origin (`CallSource`). When the origin is unknown (FaceTime, no app
  found) it is today's fallback (CRM contact on screen → call, else meeting), shown the same way.
  One tap toggles call ↔ meeting. A switch re-filters the types, clears a Vocify type that does not
  belong to the new channel, and lets the proposal run again for that channel.
- **Type** carries ✨ while it is Vocify's (history guess or model proposal); a tap opens the
  channel's types plus Interna; a pick removes ✨ and is final.
- Nothing asks the rep to choose; the line never blocks or grows the island.
- The memo is sent with `interaction_kind` = the channel shown and `typeSource` (rep | vocify).

After the call the post-call card shows the type the **call reading** chose (D7), with the same
one-tap change. A channel can also be changed there: the retag endpoint
(`POST /memos/{id}/playbook`) accepts `interaction_kind` too; a channel change drops a type that does
not belong to the new channel and re-runs nothing else.

### Settings → Tipos

Two groups, **Llamadas** and **Reuniones** (a type on both channels shows in both, marked).
Each row: name, the one-line "cómo reconocerla", playbook status (none / draft / published / paused),
and the CRM condition collapsed under "Avanzado". Adding a type asks for a name and a channel only;
Vocify drafts the `recognize` sentence from the name (editable). No role field, no required rule.

Two things Settings must also show, so configuring is not blind:
- **Whether detection is on** for the company (the flag below), in plain words at the top of the list.
- **Per type, last 30 days:** how many interactions it got and how many people changed by hand.
  A type with many corrections is the one whose sentence needs work.

### Flag

One per-company flag, `TYPE_BY_CHANNEL_ENABLED`, switches the capture pin and the candidate filter
to this design. It does not depend on `SALES_ROLES_ENABLED`. Off = today's behaviour. B1 is fixed
regardless of the flag.

### Out of scope

Visits (hidden), member-level channel settings, removing roles from the product, `visible_to_role`
(which playbooks a member sees), backfill of old memos, Jev for type detection (would need an eval
on real calls first).

## Coherence with other work (checked 2026-10-07)

- Active branches (`feat/rep-call-capture` chain, `feat/island-contact-brief`, `feat/desktop-windows`,
  `feat/island-free-text-edits`) touch `memos.py`, `call_reading.py`, `call_processor.py` and
  `DesktopMeetingProvider.tsx`, but none changes type detection or pinning. The call-capture chain is
  already merged into `origin/staging`; build from there.
- Roles (F17, `SALES_ROLES_ENABLED`) keep driving Hoy lanes, Equipo pills and which playbooks a member
  sees (`visible_to_role`). This design only stops them deciding the type. The type settings form
  drops its role field only behind the flag; `visible_to_role` keeps reading the stored role.
- The 2026-09-30 home/interaction-types spec stays valid: same two chips, same `internal` key, same
  retag endpoint. Its retag menu ("only published types") widens to every type of the memo's channel.

## Rulings (mine; Dani can undo)

- R1. (Revised in review.) `playbooks.state = 'paused'` is today the **type's** on/off switch in
  Settings, so it keeps that meaning: a paused type is not a candidate. A type with no playbook or only
  a draft **is** a candidate (label only: no score, no live help until published). A deleted type is
  not a candidate; memos already tagged keep it and still show its name.
- R2. The B1 fix ships first, alone and unflagged: smallest change, and every later step depends on the
  call reading being able to correct the live guess.

## Review (2026-10-08): flaws found in the design above, and their fixes

Checked against `origin/staging` (9115ba34) and the desktop repo.

### F1. Every type now has a channel rule, which would block the call reading
`apply_reading_type` refuses to move a pin whose source is `rule` when the type has a stored
`applies_to`. Under this design every type has `applies_to.channels`, so a capture pin made "by rule"
would freeze the type and the call reading would never decide (breaks D7).
**Fix:** the capture pin has explicit sources. `single` = the only candidate of the channel;
`crm_rule` = a CRM condition (contact new/existing/inbound, deal stage) decided it with every signal
known. Only `manual` and `crm_rule` block the reading. `single` blocks nothing except that the reading
may only move it to `internal`. `role_default` and the provisional-rule re-pin disappear under the flag.

### F2. Two detectors for `internal`
The call reading can name `internal`, and `_tag_internal` (`memo_extraction_hooks.py`, extraction's
`customerPresent`, `INTERNAL_DETECTION_ENABLED`) can tag it afterwards and overwrite the reading.
**Fix:** under the flag, `internal` comes from the call reading only; `_tag_internal` runs only when
the call reading did not run.

### F3. D7 depends on the call reading being on
The post-call assessment only exists with `INTELLIGENCE_CALL_READING_ENABLED`. Without it the live
guess or the capture pin is the final type.
**Fix:** `TYPE_BY_CHANNEL_ENABLED` is only offered for a company with call reading on; Settings shows
"detección automática: activada / desactivada" from both.

### F4. The retag endpoint and menus only accept published types
`POST /memos/{id}/playbook` returns 409 `not_published` for a type with no live version;
`retagOptions` and the post-call options filter to published. Both contradict D3.
**Fix:** accept any non-paused, non-deleted type of the memo's channel (`playbook_version_id` NULL when
it has no live version). Re-queue C04 only when the old or the new pin has a version.

### F5. Custom types and `rule_required`
`_rule_for_new_type` rejects a custom type without a rule so that no type "applies to no call".
**Fix:** replaced by "a type needs at least one channel" (call, meeting or both). Same intent, no role.

### F6. The island is native; this is a cross-repo change
The type chip is drawn by the Mac app (`MeetingPill.swift`, `TypeMenu.swift`) and the Electron
island, from `liveType` state sent by the dashboard. The channel toggle needs a new optional
`liveType.channel` field and a desktop release. **Compatibility:** an older Mac app ignores the field
and keeps the type chip working; the dashboard never requires the new field back.

### F7. Backward compatibility of `sales_motion_key` on upload
Other callers may send `sales_motion_key` meaning a real choice. **Fix:** new optional
`type_source` (`rep` | `vocify`); absent = `rep`, exactly today. The desktop always sends it. Drafts
saved on disk before the update carry no source and are sent as `vocify` (worst case: the call
reading corrects a real pick, which the rep can undo in one tap).

## Edge cases

| Case | Behaviour |
|---|---|
| Channel has **no** types (company only has meeting types, recording is a call) | No type, chip shows only the channel, no live help; Settings warns "no hay tipos de llamada". |
| Channel has **one** type | Pinned `single` at capture, no live model call; the reading may only change it to Interna. |
| Company has **no types at all** | Nothing detected; Settings empty state offers the catalog types in one click. |
| Origin unknown (FaceTime, no app found) | Today's fallback (CRM contact on screen → call, else meeting), shown as editable. |
| **Vocify dialer** call (Twilio) | Channel fixed to call, toggle not offered: it is a phone call by construction. |
| Recall bot / HubSpot CRM recording / web recorder | No island: capture pin (`single` / `crm_rule` / none), then the reading. |
| Rep switches channel live | Types re-filtered; any type not on the new channel is cleared (Vocify's **or** the rep's); proposal attempts reset; live help switches mode (`assistCallMode`). At most 4 proposals per call in total. |
| Rep switches channel after the call | Type cleared if not on the new channel and the type menu opens on the card; no AI re-run. |
| History guess points to a type of the other channel | Ignored; next fallback. |
| Type used on both channels | Candidate in both; shown in both Settings groups, marked. |
| Type renamed | Key is stable; old memos show the new name. |
| Type deleted / paused | Not a candidate; tagged memos keep it and show its name (label lookup includes deleted types, not only the active list). |
| Type's channels narrowed later | Old memos keep their type; no retro change. |
| `voice_note` and old `visit` memos | No candidates, no type; old visits keep their chip, Visit is not selectable. |
| Rep retags while the memo is still processing | Manual wins: the reading's write is conditional (`pin source != manual`) instead of read-then-write. |
| Re-extract | The reading runs again and may move `live`/`single`→Interna/reading pins; never `manual` or `crm_rule`. |
| Many types (10+) | Island menu scrolls; the prompt lists only the channel's types. |
| Flag off | Today's behaviour, except F7/B1 (live guess saved as `vocify`). |

## Build notes (2026-10-08, branch `feat/types-by-channel`)

Rulings taken while building (Dani can undo):

- B-R1. **A saved rule written for a role keeps only its channels.** Its CRM condition was decided for
  SDRs or AEs; without roles it would apply to everyone (e.g. the catalog's "AE discovery = new
  contact" would swallow every cold call). Only role-free saved rules decide by CRM, and two
  different types tied at the top decide nothing (the call reading does). Catalog defaults never
  decide by CRM.
- B-R2. **With the flag every member sees every type** in GET /playbooks (no `visible_to_role`
  filter): the island and the retag menu need the channel's full list.
- B-R3. **"Corrected" in the stats** = a manual pin that names what it replaced (`changed_from`). A
  rep's pick during the call before Vocify decided anything is not a correction.
- B-R4. **Vocify's recognition sentence is drafted after the type is created**, silently; if it fails
  the type works by name and playbook. Nothing blocks on the model.
- B-R5. **Island channel labels are singular** ("Llamada · Cold call"); Settings groups are plural.

What is built and tested (backend + dashboard): core (`channel_types.py`), migration 076
(`playbooks.recognize`, full_reset kept in sync), the type_source fix, capture / call reading /
Interna / CRM re-check, live guess and proposal, retag and channel change, Settings API and UI,
island state contract (`liveType.channel`, `onCallChannel`), Interacciones menu.

Not built here: the native island rendering of `liveType.channel` and sending `onCallChannel` (Mac
Swift app and Electron island, desktop repo), and the island post-call card's channel switch.
Until then an island shows the type chip exactly as before; nothing breaks.
