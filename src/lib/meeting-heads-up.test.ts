import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  HEADS_UP_MS,
  SHOWN_AFTER_START_MS,
  briefContactId,
  headsUpMeeting,
  islandMeeting,
  meetingWho,
  nextChangeAt,
  type UpcomingMeeting,
} from "./meeting-heads-up.ts";

const START = Date.parse("2026-10-08T09:30:00Z");

function meeting(overrides: Partial<UpcomingMeeting> = {}): UpcomingMeeting {
  return {
    id: "ev-1",
    title: "Demo Vocify",
    start_time: "2026-10-08T09:30:00Z",
    end_time: "2026-10-08T10:00:00Z",
    meeting_url: "https://meet.google.com/abc-defg-hij",
    platform: "meet",
    people: [{ name: "Marta García", email: "marta@cliente.com", hubspot_contact_id: "901" }],
    ...overrides,
  };
}

describe("meeting heads-up", () => {
  it("announces a meeting from a minute before until five minutes in", () => {
    const m = meeting();
    assert.equal(headsUpMeeting([m], START - HEADS_UP_MS - 1), null);
    assert.equal(headsUpMeeting([m], START - HEADS_UP_MS)?.id, "ev-1");
    assert.equal(headsUpMeeting([m], START + SHOWN_AFTER_START_MS - 1)?.id, "ev-1");
    assert.equal(headsUpMeeting([m], START + SHOWN_AFTER_START_MS), null);
  });

  it("back to back: the one starting first", () => {
    const next = meeting({ id: "ev-2", start_time: "2026-10-08T09:31:00Z" });
    assert.equal(headsUpMeeting([next, meeting()], START)?.id, "ev-1");
  });

  it("knows when to look again", () => {
    const m = meeting();
    assert.equal(nextChangeAt([m], START - 10 * 60_000), START - HEADS_UP_MS);
    assert.equal(nextChangeAt([m], START), START + SHOWN_AFTER_START_MS);
    assert.equal(nextChangeAt([m], START + SHOWN_AFTER_START_MS), null);
  });

  it("says who it is with", () => {
    assert.equal(meetingWho(meeting()), "Marta García");
    const group = meeting({
      people: [
        { name: null, email: "jon@cliente.com", hubspot_contact_id: null },
        { name: "Marta García", email: "marta@cliente.com", hubspot_contact_id: "901" },
        { name: "Luis", email: "luis@cliente.com", hubspot_contact_id: null },
      ],
    });
    assert.equal(meetingWho(group), "jon@cliente.com +2");
    assert.equal(briefContactId(group), "901");
    assert.equal(briefContactId(meeting({ people: [] })), null);
  });

  it("island shape carries the brief only when there is one", () => {
    assert.deepEqual(islandMeeting(meeting(), null), {
      id: "ev-1",
      who: "Marta García",
      title: "Demo Vocify",
      startsAt: "2026-10-08T09:30:00Z",
      url: "https://meet.google.com/abc-defg-hij",
      platform: "meet",
    });
    assert.deepEqual(islandMeeting(meeting(), { state: "loading" }).brief, { state: "loading" });
  });
});
