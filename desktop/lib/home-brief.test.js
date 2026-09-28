import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  HOME_BRIEF_LOADING,
  homeBriefDisplayLines,
  homeBriefRequestPath,
  shouldFetchHomeBrief,
} from './home-brief.js';

describe('desktop home brief', () => {
  const contactPage = { objectType: 'contact', recordId: '42' };
  const dealPage = { objectType: 'deal', recordId: '99' };
  const cached = {
    contactId: '42',
    brief: { text: 'Sin conversación todavía.', lines: [{ text: 'Llamar el jueves' }] },
  };

  it('shows brief lines for a contact while idle', () => {
    const lines = homeBriefDisplayLines({
      recordPage: contactPage,
      captureActive: false,
      cache: cached,
      flightContactId: null,
    });
    assert.deepEqual(lines, ['Sin conversación todavía.', 'Llamar el jueves']);
  });

  it('shows nothing while capture is active', () => {
    assert.deepEqual(
      homeBriefDisplayLines({
        recordPage: contactPage,
        captureActive: true,
        cache: cached,
        flightContactId: null,
      }),
      [],
    );
  });

  it('shows nothing on a deal record', () => {
    assert.deepEqual(
      homeBriefDisplayLines({
        recordPage: dealPage,
        captureActive: false,
        cache: cached,
        flightContactId: null,
      }),
      [],
    );
    assert.equal(shouldFetchHomeBrief({ recordPage: dealPage, captureActive: false, cache: cached, flightContactId: null }), false);
  });

  it('does not show a cached brief for another contact', () => {
    const otherContact = { objectType: 'contact', recordId: '9' };
    assert.deepEqual(
      homeBriefDisplayLines({
        recordPage: otherContact,
        captureActive: false,
        cache: cached,
        flightContactId: null,
      }),
      [],
    );
    assert.equal(
      shouldFetchHomeBrief({ recordPage: otherContact, captureActive: false, cache: cached, flightContactId: null }),
      true,
    );
    assert.deepEqual(
      homeBriefDisplayLines({
        recordPage: otherContact,
        captureActive: false,
        cache: cached,
        flightContactId: '9',
      }),
      [HOME_BRIEF_LOADING],
    );
  });

  it('requests briefs by contact id only', () => {
    assert.equal(homeBriefRequestPath('42'), '/briefs?contact_id=42&connection_id=hubspot');
  });
});
