# Calendar meeting context: who the meeting is with, before and after

Date: 2026-10-08. Status: built (backend, dashboard, Mac island on desktop `main` lineage, Electron island on `feat/mac-electron` lineage); not yet verified end to end (needs migration 077 and the Recall webhook).

## Goal

The rep's calendar tells Vocify who each external meeting is with, as HubSpot contacts:

1. **Before:** one minute before an external meeting, the island shows "Call with Marta García (Acme) in 1 min" with the contact's brief, a Join button and a Record button (what Granola does: a pop-up 1 minute before events with 2+ attendees, which opens the call and starts transcribing).
2. **After:** an island recording made during that meeting is linked to the event: the memo gets the attendees with emails and the HubSpot contact, even when no HubSpot tab was open.
3. **1:1 bonus:** with exactly one external attendee, "Them" can be labelled with that person's name on any platform.

## What exists today (checked 2026-10-08)

- **Code (staging):** Recall Calendar V2 connect/disconnect (`backend/app/api/calendar.py`, `services/meetings/calendar_bots.py`). Events are read from Recall only to schedule bots; nothing is stored. `RecallClient.list_calendar_events` and `get_calendar_event` exist.
- **Attendees → HubSpot:** only for calendar-bot memos, after the bot finishes (`webhooks.py`, `services/meetings/attendees.py`). `enrich_attendees_with_hubspot` replaces names with HubSpot names; it does not keep the contact ID nor link the memo.
- **Island:** never reads the calendar. Recordings get a contact only from the CRM tab on screen. Briefs (`/briefs`, `/briefs/meeting`, `/contacts/{id}/recent-activity`) need a contact ID.
- **Island brief on the Mac:** the dashboard sends `onScreen.brief` lines (`DesktopCallProvider.tsx`), but the Mac rendering is on desktop branch `feat/island-contact-brief` (1 commit, not on `main`).
- **Config (Railway, staging and production):** set: `RECALL_API_KEY`, `RECALL_REGION`, `RECALL_BOT_ENABLED`, `GOOGLE_CALENDAR_CLIENT_ID/SECRET`. Missing: `RECALL_WEBHOOK_SECRET` (the webhook still works: it re-reads everything from Recall with our key) and `MICROSOFT_CALENDAR_CLIENT_ID/SECRET` (no Outlook).
- **Database (production):** `calendar_connections` exists; 1 row (Google, connected 2026-09-30, auto_join on). 0 bot memos.
- **Webhooks:** no request reached `/api/v1/webhooks/recall` in the last 7 days of production or staging HTTP logs. Most likely the Recall webhook endpoint is not configured in Recall's dashboard (not visible from here). Without it, calendar changes never reach us.

## Design

### 1. Connecting the calendar is separate from the bot

Today connecting is behind the `RECALL_BOT_ENABLED` company flag and lives under "the bot joins my meetings". Calendar context must work with the bot off:

- Connect/disconnect available to every rep (Settings → Calling, existing `CalendarSettings` card), flag only gates the bot switch.
- New connections default `auto_join = false` (decision D1).

### 2. Store upcoming events

New table `calendar_events` (next free migration number; mirrored in `full_reset.sql`):

| column | |
|---|---|
| `id` uuid pk | |
| `recall_event_id` text unique | Recall's event ID |
| `user_id`, `company_id` | owner |
| `start_time`, `end_time` timestamptz | |
| `title` text | from `raw.summary` (Google) / `raw.subject` (Graph) |
| `meeting_url` text | Recall's `meeting_url` |
| `attendees` jsonb | `[{email, name, external, hubspot_contact_id}]`, rooms and the rep excluded |
| `is_deleted` bool | cancelled, declined by the rep, or deleted |
| `updated_at` | |

Filled by the existing `sync_calendar` (full sync on connect, delta on `calendar.sync_events`), so no new Recall calls. Keep events from 1 day ago to the sync horizon; delete older rows on each sync. Service role only, like `calendar_connections`.

"External" reuses `calendar_bots` logic: email domain differs from the rep's calendar email; rooms excluded.

### 3. Match external attendees to HubSpot contacts

At sync time, for each external email without a match yet: `HubSpotSearchService.find_contact_by_email` through the company's HubSpot connection; store `hubspot_contact_id` and the HubSpot name on the attendee. Only new or changed emails are looked up; a miss is stored as `null` and retried on the next change to the event. Failures never block the sync (same as `enrich_attendees_with_hubspot`).

Pipedrive: same shape later through the CRM adapter (out of scope here).

### 4. API

- `GET /calendar/upcoming?hours=12`: the rep's next events with at least one external attendee and a meeting URL, not deleted, with attendees and contact IDs.
- `GET /calendar/at?time=<iso>`: the event a recording starting at `time` belongs to (rule in §6), or null.

### 5. Island: "in 1 minute"

- The dashboard (desktop shell) fetches `/calendar/upcoming` on load and every 5 minutes, and schedules a local timer at `start_time - 60 s` per event.
- At that moment the island shows the meeting: title, the main external contact's name and company, the brief lines from `/contacts/{id}/recent-activity` (same `islandBrief` as the call offer), **Join** (opens `meeting_url`) and **Record** (starts the recording linked to this event).
- Dismissed by the rep, or automatically when the event starts plus 10 minutes.
- Requires `feat/island-contact-brief` merged on the desktop `main` for the Mac rendering.

### 6. Linking a recording to an event

When an island recording starts (or Record is pressed on the pop-up, which passes the event ID directly):

- Candidate events: the rep's events not deleted, with `start_time` within 15 minutes before or after the recording's start (Granola links a call that starts within 15 minutes of a scheduled meeting).
- More than one candidate: prefer the one whose meeting URL matches the call app (zoom.us for Zoom, meet.google.com for a browser), then the closest start.
- The memo stores `calendar_event_id` and `attendees` (with emails and contact IDs).
- Contact: the CRM contact on screen wins; otherwise, the single external attendee with a HubSpot match (decision D2 for several).
- With exactly one external attendee and no Zoom/Meet speaker reading, the prospect lines are labelled with that attendee's name.

### 7. Bot and island on the same meeting

Today a rep recording with the island while a calendar bot is in the call gets two memos. When a recording is linked to an event that has a scheduled bot, decision D3 says which wins.

## Decisions (taken while building, 2026-10-08; Dani can revisit)

- **D1:** a new calendar connection starts with the bot off (`auto_join = false`, migration 077 changes the column default); reconnecting keeps the rep's switch.
- **D2:** the memo is linked to a contact from the calendar only when exactly one outside attendee matched a HubSpot contact; with several, none is guessed (the rep picks in the review). The CRM tab on screen always wins.
- **D3:** unchanged: an island recording and a calendar bot on the same meeting still make two memos.
- **D4:** (changed 2026-10-08 by Dani) the heads-up is for every meeting with someone besides the rep and a call link, internal ones included: an internal meeting is typed "internal" on its memo. Only outside people are matched to HubSpot (the brief is for them), and the bot still joins only meetings with people from outside.
- **Heads-up window:** from 1 minute before the start until 5 minutes after; the island opens once per meeting for 60 s (the pointer holds it); a closed meeting is not shown again; a call or recording in progress is never interrupted.
- **Freshness:** `/calendar/upcoming` re-syncs from Recall when the last full sync is over 5 minutes old, so it works even without Recall's webhook.
- **Recording link:** by start time (meeting starting within 15 minutes, or already running), same-app meeting first. The 1:1 "Them = attendee's name" labelling is not built.

## Setup Dani still has to do

1. In Recall's dashboard (EU region), add the webhook endpoint `https://api.getvocify.com/api/v1/webhooks/recall` with the calendar events; set its signing secret as `RECALL_WEBHOOK_SECRET` in Railway (staging and production share one Recall workspace: decide whether staging gets its own endpoint).
2. For Outlook users: Microsoft app registration and `MICROSOFT_CALENDAR_CLIENT_ID/SECRET`.
3. Ask Recall support to enable participant emails (needed for the bot transcript, not for this feature).

## Out of scope

Pipedrive matching, Windows island, Electron, storing past meetings beyond 1 day, in-meeting notetaker pop-up for calls not on the calendar (the island already offers Record when a call app takes the mic).

## Tests

- Backend: event → row mapping (Google and Graph `raw`), external/room/rep filtering, HubSpot match cached and failure-tolerant, `/calendar/at` rule (window, URL preference, ties), delete of old rows.
- Dashboard: pop-up timer scheduling and cancellation, Record from pop-up passes the event ID, memo upload carries `calendar_event_id`.
- Live: one real Google Calendar with an external test meeting: pop-up at -1 min, Join, Record, memo linked to the HubSpot contact without a HubSpot tab open.
