# Vocify UX and product completion — code review and discovery plan

> For agentic workers: execute this discovery plan journey by journey. It does not authorize merging to main, deploying, changing company flags, sending customer emails, or changing customer CRM records. Use the existing Reticle verification workflow for live application evidence. Implementation follows a reproduced finding and its acceptance criterion.

**Goal:** establish what remains before the intended SDR, AE, manager, and cross-surface journeys work coherently, with evidence rather than completion labels.

**Architecture:** trace each promised outcome from its entry point through UI, request, persisted result, and subsequent consuming surfaces. Review a fixed remote snapshot separately from the user's dirty main checkout. Distinguish code-confirmed gaps, local function reproductions, live verification, and scope decisions.

**Tech stack:** React/TanStack Query, shared UI components, FastAPI/Postgres, Chrome extension, Electron/macOS capture, CRM adapters, Resend, Recall, Reticle.

## Global constraints and review scope

- **No merge to main.** No application implementation, deployment, flags, database, customer records, or external messages were changed in this review.
- Reviewed `origin/staging` and `origin/claude/gallant-rubin-akpmoi` at **69428d7a9a12adb01f2be50d32e71eb84184eaed**, freshly fetched September 28, 2026.
- Local `main` remains at `4b1d777c`; its existing staged/unstaged work is separate evidence, not remote implementation.
- Code inspected from `/tmp/vocify-progress-69428d7a`, exported directly from that Git revision. Source links below pin that revision, not the local main files.
- Apply `.cursor/skills/vocify-ux-coherence/SKILL.md`: one obvious primary action, concise grounded copy, designed empty/loading/error states, proportional visual weight, continuity across surfaces, stable lists, usable transcript turns.
- Scope authority: original V1 feature specifications and contracts, then explicit `00-decisiones.md` decisions, then Lista 2/F16 and Lista 3 amendments. Later amendments can change earlier decisions; an old unchecked task is not automatically missing work.
- Apple signing/notarization/public distribution and Windows are explicit exclusions, not undisclosed failures of Lista 3. F03 approval and the synthetic F09 evaluation decision are already resolved; do not reopen them.
- This is a **code and product review**, not a visual approval. No live browser/native walkthrough was performed this turn. Layout polish, focus behavior, animation, real credentials, database state, and installed-extension behavior remain unverified.

## Assessment

**The UX/UI and end goals are not all complete.** There is substantial implementation, but several producer/consumer connections are unfinished. The earlier conclusion that remaining work was mainly activation was too generous.

All fourteen Lista 3 feature tasks have implementation commits. That establishes implementation presence, not delivery of all promised behavior. Examples below include a new sending behavior connected to old misleading copy, a new route without its required layout host, and new report fields ignored by the existing web renderer.

### Product goals, assessed separately

| End goal | What exists | What prevents claiming completion |
|---|---|---|
| Capture calls, meetings, visits into one usable conversation | Common post-extraction pipeline, WhatsApp integration, desktop capture code, Recall bot integration | Native capture/overlay recovery and actual bot lifecycle are not verified here. Cross-surface identity, audio, transcript, and review continuity still need a real journey. |
| Keep CRM updated with minimal administration | Review/approval, C04 commitments, confirmations, handoffs and provider writes | Handoff CRM failures are hidden by the frontend; retries, duplicate actions, and partial provider failures need live verification. |
| Give every rep a useful daily workspace | RepHome, brief, selection, dialer integration, follow-up, role-specific deal reads | Manager personal Today loses its wide-screen panel; AE cards lack identity/actions; hidden call rows still participate in AE selection; Ask does not preserve the full visible conversation. |
| Coach against the company's actual sales process | Playbook storage/versioning, scoring/debrief, objection examples, report/team views | The normal import path produces one generic process step and cannot author structured objection guidance. Published playbooks have no normal read/edit path in Settings. Web reports ignore new role-specific metrics. |
| Deliver a coherent and trustworthy experience | Shared UI, tokens, bilingual catalog, loading/error helpers, some reduced-motion/list handling | New adapter behavior and old shared presentation diverge. Several error paths suppress or never render the explanation. Actual visual/focus/motion consistency has not been assessed. |
| Meet the plan's adoption/productivity thresholds | F16 states measurable GA criteria | No evidence of achieved thresholds; the planned home-resolution attribution is absent from request and API schemas. Functional tests cannot establish adoption or time saved. |

## Confirmed code findings

“Confirmed” here means the code path or pure-function output is established. It does **not** mean a live customer session reproduced it. P1 indicates a broken or materially misleading core journey; P2 indicates incomplete usability, recovery, or product coherence.

### UX01 — P1: a button promising to open email can send it immediately

- `shared/ui/components/followup.js:49` always labels the email action **“Abrir en el correo”** / “Open in mail.”
- `src/components/dashboard/FollowupCard.tsx:59` changes that action to `sendFollowup()` when `FOLLOWUP_SEND_ENABLED` is active.
- After a successful direct send, the shared renderer still says **“Abierto en el correo”**, because line 31 only distinguishes WhatsApp from every other channel. `vocify_email` is not distinguished.
- The same card shows a success toast for any successful send API response. The API can return an existing in-flight claim without a completed send (`backend/app/api/followup.py:169–173`); `followup_view` does not expose that send state.
- **Impact:** the person can expect to review in their mail client but instead transmit the email; the resulting UI does not accurately explain what happened.
- **Commit trace:** direct sending added in `8a2c6ddd`, request handling refined in `b162fbff`; shared opening copy remains from `4e507193`.
- **Local reproduction:** actual `renderFollowup` + `renderToString` returned `Abrir en el correo` for ready email and `Abierto en el correo` for `status=sent, channel=vocify_email`.
- **Acceptance:** opening a draft and transmitting an email have distinct labels and outcomes; busy/uncertain/failed/sent states reflect the server. Exercise web, extension, and desktop adapters without assuming they all send directly.
- [Shared renderer](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/shared/ui/components/followup.js#L28) · [Web adapter](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/src/components/dashboard/FollowupCard.tsx#L45)

### UX02 — P1: manager personal Today has no contact panel at wide widths

- `DashboardHome.tsx:24` sends a manager who also sells to `/dashboard/today`; `App.tsx:191` renders `RepHome` there.
- `DashboardLayout.tsx:77` only creates the panel target when the path is exactly `/dashboard`.
- `useHomeSelection.ts:64` chooses a Sheet only below 1280px. At wide widths, `ContactPanel.tsx:581` returns null when no target exists.
- **Impact:** the manager's personal workspace can show the list but loses the contact preparation, follow-up, and panel actions on desktop-sized screens.
- **Commit trace:** panel host introduced in `8e5fb8d4`; new manager route introduced in `7a0e445f` without updating its host condition.
- **Acceptance:** `/dashboard/today` supports the same selected-contact workflow as rep `/dashboard`, with a right panel at 1440px and Sheet at 1024px, including Ask and an ongoing call.
- [Layout condition](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/src/components/dashboard/DashboardLayout.tsx#L77) · [Panel fallback](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/src/features/today/components/ContactPanel.tsx#L554)

### UX03 — P1: playbook setup does not deliver the structured, maintainable process consumers need

- F08 specifies text/PDF/audio, reviewable steps/criteria, recovery of drafts, and published versions.
- `PlaybooksSection.tsx:69` supports only text/PDF in the UI. Its import response retains text and warning state, not an automatically resumable draft identity. A separate manual “import ID” field exists.
- `renderEditorBody` returns null for a published motion (`:152`); the surrounding screen renders status/goal/version, not the published contents or an edit/create-next-version action. Members likewise cannot read the actual process there.
- `GET /playbooks` returns statuses/goals, not the process content. `save_playbook_draft` in migration 040 creates **one** step with ID `imported`, the entire input as its criterion, and **one** entry with category `process`. No later checked-in migration replaces that function.
- **Impact:** normal UI setup cannot supply separately reviewable sales steps and categorized objection guidance for adherence, “what to say,” and coaching. A company could have structured data manually seeded outside this path; this finding does not claim its live data is necessarily generic.
- **Commit trace:** generic persistence from `0367e6fa`/`29d81a0e`; Lista 3 tabs in `57416ee4` preserve the limitations.
- **Acceptance:** import a three-step process with price/timing objection guidance; inspect the stored structured version; read it as a member; revise it as a manager; refresh/reopen the draft; confirm an ongoing capture stays pinned to its original version. Include audio and malformed PDF.
- [Editor](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/src/features/playbooks/components/PlaybooksSection.tsx#L151) · [Persistence](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/backend/migrations/040_company_playbooks.sql#L82)

### UX04 — P1: the AE's daily deal workflow is not integrated with identity and selection

- `_deal_items` returns contact/deal IDs, a generic reason and URL, but no `contact_name` or `company_name` (`today.py:434–445`). Existing name enrichment runs **before** these separate deal items are created (`:584`).
- `DealCard` uses `CardBody`, whose title falls back to “Contacto.” Its only control expands a brief; it does not render the supplied CRM URL, call action, or select the shared contact panel (`TodayItemList.tsx:125–138`).
- `RepHome` adds deals outside `composeHome`/`homeRows`, while hiding the calls section for AE **after** building selection (`:269–272`, `:365–389`). The shared composition still consumes legacy flat `today.items` and priorities.
- **Local reproduction:** with a flat call item and AE sections, the actual `composeHome → homeRows → homeSelection` chain selects that call. AE rendering then hides the calls list. Deals are not selectable rows in this chain.
- **Impact:** different deals can look like generic “Contacto” cards; the AE lacks an obvious next action and can have a selected contact absent from the visible list. The SDR-history panel added by T4 is not reachable directly from a deal card.
- **Commit trace:** T6 `49f0a36b`; AE call-list hiding in `c1285b02` did not change shared composition/selection.
- **Acceptance:** two named AE deals, one handed off and one own deal, can be distinguished, opened, prepared, and acted on; keyboard selection only visits visible rows; empty/partial states include deal-read coverage. General retains all intended sections.
- [Deal producer](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/backend/app/api/today.py#L434) · [Deal renderer](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/src/features/today/components/TodayItemList.tsx#L125) · [Home integration](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/src/features/today/components/RepHome.tsx#L266)

### UX05 — P1: handoff success hides failed or unmapped CRM ownership

- D7 explicitly requires an “owner unmapped” warning when the Vocify handoff succeeds without CRM reassignment.
- Backend returns `crm_owner_status` (`done`, `skipped`, `unmapped`, `failed`); the frontend type includes it.
- `HandoffAction` awaits `handoffsApi.create(...)` without reading the response, then unconditionally sets `done` (`ContactPanel.tsx:117–139`). No rendering of `crm_owner_status` was found in frontend code.
- **Impact:** the SDR is shown success while the CRM owner can remain unchanged, with no explanation of the partial outcome.
- **Commit trace:** T3 `1d421ab7` and `6d1633c5`; later owner lookup changes do not consume the result in UI.
- **Acceptance:** distinguish successful handoff from CRM ownership result; show recovery for unmapped/failed ownership without creating a duplicate handoff or repeating a completed effect.
- [Handoff UI](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/src/features/today/components/ContactPanel.tsx#L117) · [API result](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/backend/app/api/handoffs.py#L151)

### UX06 — P2: Ask loses visible conversation continuity and suppresses errors

- Closing Ask unmounts `AskPanel` (`DashboardLayout.tsx:307`). Its draft and full `lines` array live only in component state.
- On reopen, it fetches **only the latest stored turn**, restoring at most its question and answer (`AskPanel.tsx:85–115`). Earlier visible turns and an unsent draft disappear.
- A failed confirmation writes `view.notice` (`:217`), but the component never renders that field. Sending has `try/finally` without a handled error state; restore errors are swallowed.
- **Impact:** users cannot rely on closing/reopening the assistant to preserve their work or explain a failed action, contrary to F07's stated continuity/recovery behavior.
- **Commit trace:** `aa474905` restored the latest question but not full history; later `dce781c1`/`980b1311` add capabilities/link rendering without fixing continuity.
- **Acceptance:** three turns plus an unsent draft survive close/reopen and reload according to the agreed persistence boundary; 401/500/failed confirmation have actionable visible states; retry preserves turn/operation identity.
- [Ask state and restoration](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/src/features/ask/components/AskPanel.tsx#L73)

### UX07 — P1: role-specific reports are not consistently delivered or defined

- Backend T12 adds `snapshot.sections` and handoff/meeting/deal/proposal metrics. Email presentation reads those new fields.
- Web `ReportSnapshot`/`ReportMetricCellKey` do not include them. `reportPagePresentation` always iterates the old fixed label map (`report-snapshot.ts:184`).
- **Local reproduction:** an AE snapshot requesting `meetings_held, deals_in_progress, proposals_sent, deals_won` renders web rows `attempts, connected_calls, meetings_agreed, deals_won, adherence`.
- Separately, reports count “deals in progress” as the number of active handoff rows (`daily_snapshot.py:160–177`), while Hoy includes handoffs **plus own deals with memos**, deduplicated and filtered by observed closed stage (`today.py:381–445`). These definitions can disagree for the same AE.
- “Proposals sent” counts `followup.status == sent` on period memos; legacy “opened in mail” also sets that status. It is not by itself evidence of a transmitted proposal. Sending-date boundaries also need a dedicated check.
- **Commit trace:** T12 `07148cd1`, review `c8710e4d`; web report mapping predates those changes.
- **Acceptance:** one persisted snapshot renders the same intended role-specific facts in web/email; own deals, duplicate handoffs, closed stages, external draft opening, actual sends, and period boundaries have explicit consistent definitions.
- [Web renderer](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/src/lib/report-snapshot.ts#L74) · [Email renderer](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/backend/app/services/reporting/presentation.py#L54) · [Report metric source](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/backend/app/services/reporting/daily_snapshot.py#L129)

### UX08 — P2: team visibility and drilldown are only partly usable

- TeamInsightsPage and TeamRepDetailPage explicitly permit members with `visibility=team`.
- `navItemsFor` only shows Insights to owner/admin and has no visibility input; DashboardLayout does not pass visibility. Such a member has no normal main-navigation entry to the permitted team page.
- Rep detail renders handoffs as raw `contact_id` and backend status, with no contact name/link (`TeamRepDetailPage.tsx:45–54`); the heading does not identify the selected rep by name. It fixes `motion:null` and supplies no per-flow filter despite T13's requested flow-specific detail.
- **Acceptance:** each permitted role can discover its allowed view; each drilldown identifies the person, contact, flow, date/period and next useful action without exposing internal identifiers as the primary content.
- [Navigation](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/src/lib/nav.ts#L39) · [Rep detail](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/src/pages/dashboard/TeamRepDetailPage.tsx#L45)

### UX09 — P2: onboarding has no useful recovery from a failed state read

- The error branch offers only navigation to `/dashboard` (`OnboardingWizard.tsx:71–79`).
- If the cached company still has `needsOnboarding=true`, DashboardHome immediately redirects back to onboarding. There is no explicit retry control or alternative recovery on that screen.
- CRM/playbook steps navigate out of the wizard; completion, return, re-entry and skipped-step persistence need a live walkthrough. Skipping is allowed by the plan and is **not** itself a defect.
- **Commit trace:** T9 `c9c3b65e`, fixes `9befc393`.
- **Acceptance:** failed read can be retried or escaped without a redirect loop; leaving to connect CRM/publish a process returns to the correct useful step without losing work or requiring the user to rediscover the route.
- [Onboarding error](https://github.com/ToDa-Inc/getvocify/blob/69428d7a/src/pages/dashboard/OnboardingWizard.tsx#L71)

## Additional evidence gaps and scoped questions

- **F16 business success is not measured by the passing suite.** Its spec requires ≥70% resolutions from home, median first action ≤60s, ≥60% same-day follow-ups, ≤10% confirmations older than 24h, and ≥4 active days/week. `todayApi.resolve` and `ResolveBody` lack the specified `surface=home` attribution. No achieved cohort metrics were reviewed. Discover whether measurement exists outside this code before designing instrumentation.
- **AI quality:** committed F02 model runs name `followup_v2`; flow-specific sending uses `followup_v3`. Test both roles, languages, thin input and real rep style against the new prompt. Do not claim the v2 runs validate v3.
- **Visual coherence:** hardcoded language remains, e.g. `Reproducir tramo` in PostInteractionBrief and English integration descriptions. Brief progress is a bare percentage sequence, and best-call cards omit the supplied date. These need a screen-level hierarchy/readability audit rather than speculative restyling.
- **Failure honesty:** FollowupCard hides unavailable/read-failed data; playbook initial fetch failures are swallowed; AE deal-read failures become an empty array. Trace whether each screen distinguishes unavailable from genuinely empty and offers recovery.
- **Capture/Recall/desktop:** code presence is not proof of capture permissions, recovery, overlay visibility/focus, installed artifacts, bot admitted/failed/completed states, or one usable conversation after completion. F12's native criteria remain open.
- **Product vision versus contracted scope:** `EXPERIENCIA_PRODUCTO.md` describes manager feedback on exact moments becoming future coaching guidance. The reviewed Lista 3 implementation does not establish that complete loop. Reconcile it explicitly as required for this release or a named subsequent scope; do not silently expand Lista 3 or claim the vision is fulfilled.

## Existing progress that should be preserved

- RepHome has shared composition, selection/keyboard logic, call locking, after-call processing, section limits, and reduced-motion-aware behavior. Audit the actual integration instead of replacing the workspace.
- Shared follow-up and transcript components, existing tokens, Sheet/panel patterns, and coaching/report components are reusable foundations.
- The earlier meeting-proposal read-error object now supplies `phrases`; the earlier frozen priority clock now uses the real clock; playbook import lookup now includes the company. Do not recycle those old findings as current defects.
- Original reports and closure tables have stale or contradictory labels. The issue is evidence reconciliation, not deleting the plan or treating every old unchecked box as missing implementation.

## Discovery execution plan

Each task produces a reviewed evidence record before a fix is counted as complete. Record: snapshot/deployment SHA; environment and relevant flags; role; viewport; fixture IDs; expected outcome declared before action; observed DOM/network/state; screenshot when relevant; verdict; linked defect or explicit scope decision. A test-fixture reproduction and a live walkthrough are separate columns.

### Task 1 — Establish the environment and one canonical acceptance ledger

**Read:** original V1 contracts/decisions/gates; Lista 2; F16 spec/design; Lista 3; PENDIENTES; actual deployment/build identifiers and company feature capabilities.

- [ ] Confirm the frontend and backend revision actually under test. A Git branch tip is not a deployment identifier.
- [ ] Read migration/schema state and effective flags without changing them. Include 054–061, rep workspace, role-specific flows, CRM owner writes, direct email and Recall.
- [ ] Identify whether staging shares data or sends calls to production; the checked-in pending list says it does. Document boundaries before any write-based walkthrough.
- [ ] Establish a dedicated test company/accounts for SDR, AE, General, owner/admin who also sells, and member with team visibility. Use a controlled mailbox and CRM test records for sending/writes; do not use real prospects.
- [ ] Create one row per acceptance criterion with status `code gap`, `code present/live unverified`, `live pass`, `blocked`, or `explicitly deferred`. Attach the scope source and evidence date. Never turn a documentation checkbox into a runtime pass.

**Exit:** a reproducible test target and ledger covering all original delivery gates plus Lista 2/F16 and Lista 3 additions, without applying flags or migrations merely to obtain a green result.

### Task 2 — Prove company setup produces usable coaching inputs

**Inspect/target:** OnboardingWizard, TeamPage, PlaybooksSection, playbooks API/store/imports, migration 040, CompanyService onboarding state.

- [ ] Start with a new company; connect a test CRM, invite SDR/AE, assign routing, and leave/re-enter each linked setup screen.
- [ ] Import a three-step process with separate price/timing guidance; review/edit/publish it. Repeat with audio, valid PDF, encrypted PDF and a failed request.
- [ ] Reload a draft; inspect actual persisted steps/categories/source references. Open the published version as member and revise as manager.
- [ ] Start a capture on version A; publish B; verify the capture/score still references A.
- [ ] Inject an onboarding read failure; verify visible retry and a usable escape path.

**Expected result:** the manager can configure and maintain a meaningful process; members can understand it; consumers receive structured, versioned content. Log UX03/UX09 separately from environmental prerequisites.

### Task 3 — Prove each role can run its day

**Inspect/target:** DashboardLayout/DashboardHome/App routes, RepHome, shared home composition, useHomeSelection, ContactPanel, TodayItemList, today deal/name producers, usePanelPrimary.

- [ ] At 1440px and 1024px, run SDR `/dashboard` and manager `/dashboard/today`: choose a contact, read preparation, open Ask and return, start a controlled call, navigate, end it, and continue.
- [ ] Run AE with two named deals and no visible calls; then with legacy flat call items present. Compare visible rows with selected row and keyboard actions.
- [ ] Run General with calls/meetings/deals; test 0, 1 and >7 items, no CRM, missing phone, CRM error, and stale refresh during a call.
- [ ] Verify names, reason, next action, brief, SDR handoff history, and contact/deal identity in each row/panel. Confirm the advertised action actually initiates the intended behavior.
- [ ] Resolve/undo across two tabs; inspect server version and focus. Verify reduced motion and keyboard handling inside editable fields. Smoke-test narrow screens for regressions without inventing a new mobile F16 scope.

**Expected result:** a visible contact and its action stay aligned; panels exist on every intended route; no hidden selection, premature list movement, or failed read presented as nothing to do. This directly exercises UX02/UX04.

### Task 4 — Prove handoff and CRM administration end to end

**Inspect/target:** HandoffAction, handoffs API/services, owner writer, memo visibility, meeting acceptance, Hoy reconciliation, confirmation jobs.

- [ ] SDR hands off a controlled contact; it leaves SDR work and reaches the intended AE with its conversation history.
- [ ] Repeat with no assigned AE, no matching CRM owner, provider failure, duplicate click, and uncertain timeout.
- [ ] Observe both Vocify ownership and actual CRM ownership separately; verify the UI explains partial success and retry does not duplicate effects.
- [ ] Confirm meeting/stage after autoapproval, undo within the window, and re-read from another surface.
- [ ] Verify unauthorized reps cannot read another contact's history; team visibility allows the intended discovery/navigation without granting management.

**Expected result:** correct person, one intended effect, preserved evidence, truthful partial state, and an obvious next step. Closes UX05 and permission/discovery portions of UX08.

### Task 5 — Prove follow-up and Ask preserve intent and work

**Inspect/target:** FollowupCard, shared followup renderer/i18n, followup API/view/send, extension/desktop adapters, AskPanel and web-session APIs.

- [ ] Compare follow-up flag-off opening and flag-on direct sending. Read the exact button label before acting; use only a controlled recipient.
- [ ] Edit, allow polling, switch memo, return, send once, retry, and observe a concurrent in-flight response. Verify draft retention, actual server outcome, mailbox receipt, CRM note, and list removal independently.
- [ ] Test missing email, unavailable draft and API read error; a disappeared card is not a recovery state.
- [ ] Ask three linked questions, leave an unsent draft, close/reopen, then refresh. Test pending turn, 401, failed POST, failed confirmation and retry. Assert the displayed history, draft, notice, and operation identity.
- [ ] Run/record v3 follow-up evaluations for SDR and AE with sparse evidence, real style examples and ES/EN, separately from existing v2 runs.

**Expected result:** every control does what its label promises, no user work vanishes, and failure never looks like successful completion. Closes UX01/UX06 and the current prompt evidence gap.

### Task 6 — Prove coaching/reporting is meaningful and consistent

**Inspect/target:** score/brief jobs, playbook consumers, ReportPage/report-snapshot, daily/weekly snapshot loaders and presentation, TeamInsightsPage, TeamRepDetailPage, Ask team tools, PlaybookPage, ReportBell.

- [ ] Use known conversations from the configured process: one easy meeting, one well-handled objection, one missed step, one ambiguous statement, and one unavailable audio recording.
- [ ] Trace evidence → score → short feedback → playable moment → team aggregation. Confirm that a meaningful reviewed process, not a generic imported paragraph, supplies the criteria.
- [ ] Generate SDR/AE/General snapshots with known counts; open each via the bell and compare web/email/Ask for the same scope and period.
- [ ] Include an own deal without a handoff, duplicate handoff contacts for one deal, a closed deal, opened-but-unsent mail, actual sent proposal, and a send outside the memo's capture period.
- [ ] Open a named rep from the manager overview; inspect each flow, identifiable handoffs, recent conversations and evidence. Verify role permissions and entry points.
- [ ] Review wording and visual hierarchy: actionable feedback before unexplained scores, timestamps/context, no invented zeros or unsupported conclusions.

**Expected result:** the same business concept has the same definition and value across the product, with useful evidence and a next action. Closes UX07/UX08 and assesses the coaching end goal.

### Task 7 — Prove capture and cross-surface continuity

**Inspect/target:** RecordPage/RecallBotForm; capture API and hooks; desktop host/capture/review/overlay; extension contact/review/transcript/follow-up; shared UI.

- [ ] Capture a controlled conversation through each required channel: dialer, extension, desktop meeting, WhatsApp voice visit, and configured Recall bot.
- [ ] Confirm one canonical memo and correct interaction kind/contact/turn timing; follow it into review, CRM, follow-up, brief, Hoy and report.
- [ ] Exercise offline/restart/retry, permission refusal, bot not admitted, delayed transcription and duplicate completion.
- [ ] On the actual native desktop, verify minimized/fullscreen overlay, focus, clipping, Stop/double-click, one STT session, and no stale prior-session suggestion.
- [ ] Record installed extension/app version and artifact source. Keep waived signing/Windows requirements explicitly separate from required internal Mac behavior.

**Expected result:** the person can finish the same interaction across the intended surfaces without data loss, duplicate work or misleading state. A unit test of the overlay reducer does not close native UI acceptance.

### Task 8 — Audit visual coherence and measure the end goals

**Inspect/target:** existing tokens and shared components, all screens exercised above, F16 GA criteria, existing analytics/event storage if any.

- [ ] Capture representative populated, empty, loading, error and partial screens in ES/EN at supported widths. Check typography, density, primary action, focus order, labels, overflow and transitions against the existing design.
- [ ] Count actions and context switches in the actual setup → first call → review → follow-up → next-contact journey. Distinguish unavoidable provider handoff from missing product integration.
- [ ] Locate or specify the minimal events needed for the five F16 metrics. Explicitly distinguish external email opening from actual sending before calculating “sent same day.”
- [ ] Measure a pilot cohort and observation window; report achieved values or “not measured,” never infer adoption from functional tests.
- [ ] Reconcile vision-only items, such as manager feedback becoming future guidance, into current acceptance or an explicit next scope.
- [ ] Publish the final remaining-work ledger: confirmed defects with repros, missing behavior, external setup, evidence gaps, deferred scope, and completed journeys. Estimate repair effort only after reproduction and scope are established.

**Exit:** an evidence-backed release-readiness decision, with no merge or deployment as part of this plan.

## Verification rules and existing evidence

- Fresh checks from the preceding review at the same Git SHA: **2,151 backend tests passed; 317 frontend unit tests passed; build passed; TypeScript reports 39 errors.** Existing local dependency environments were reused. These results do not prove runtime integration or visual quality.
- This turn executed actual pure rendering/composition functions for follow-up copy, AE selection, and web report fields; all three exposed the mismatches recorded above. They are not live Reticle verdicts.
- Test review found strong logic/adapter coverage, but the cited frontend unit tests do not mount the complete route/layout/component journeys. For example, Ask reducer tests cannot prove that AskPanel renders its notice or retains its component-local draft.
- In live discovery, declare the expected consequence before acting. Use Reticle `reticle_act_and_wait`/`reticle_assert` for verdicts, and inspect network/store/console evidence. `unknown` and `no-fault` are not passes. For native-only behavior, record the appropriate native evidence explicitly.
- If Reticle is disconnected, follow this repo's setup/recovery instructions; do not treat an installation or connected session as completed verification. Do not start a second dev server or assume a listening server has the current bundle.
- Documentation-only change: Reticle verification was not required for writing this plan. All pending application verification remains explicitly pending.

## Recommended order

Establish the environment/ledger first. Prioritize the misleading email action, manager panel routing, playbook producer, AE workflow, and report parity. Then finish recovery/permission journeys and cross-surface/native acceptance. Visual cleanup follows verified end-to-end behavior; adoption measurement follows a defined pilot. None of these stages authorizes merging to main.
