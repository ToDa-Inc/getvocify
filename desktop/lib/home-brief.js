import {
  BRIEF_LOADING,
  briefForContact,
  briefRequest,
  contactBriefDisplayLines,
} from '../renderer/shared/ui/brief.js';

export const HOME_BRIEF_LOADING = BRIEF_LOADING;

export function homeBriefContactId(recordPage) {
  if (!recordPage || recordPage.objectType !== 'contact') return null;
  const recordId = recordPage.recordId;
  if (recordId == null || recordId === '') return null;
  const id = String(recordId).trim();
  return id || null;
}

/** Text lines for the home brief surface (0–3 facts, or one loading line). */
export function homeBriefDisplayLines({ recordPage, captureActive, cache, flightContactId }) {
  const contactId = homeBriefContactId(recordPage);
  if (!contactId) return [];
  return contactBriefDisplayLines({
    objectType: recordPage.objectType,
    contactId,
    captureActive,
    cache,
    flightContactId,
  });
}

export function shouldFetchHomeBrief({ recordPage, captureActive, cache, flightContactId }) {
  const contactId = homeBriefContactId(recordPage);
  if (!contactId || captureActive) return false;
  if (briefForContact(contactId, cache)) return false;
  if (flightContactId === contactId) return false;
  return true;
}

export function homeBriefRequestPath(contactId) {
  return briefRequest(contactId);
}
