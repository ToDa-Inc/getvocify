/**
 * Who a memo belongs to — from the memo itself, not the live HubSpot tab.
 */

function str(value) {
  return String(value ?? '').trim();
}

export function memoContactName(memo = null, preview = null) {
  return str(
    preview?.selected_contact?.name
    || preview?.selected_contact?.email
    || memo?.extraction?.contactName
    || memo?.extraction?.contact_name,
  );
}

export function memoCompanyName(memo = null) {
  return str(memo?.extraction?.companyName || memo?.extraction?.company_name);
}

export function memoListTitle(memo = null, preview = null) {
  return memoContactName(memo, preview) || memoCompanyName(memo) || 'Untitled conversation';
}

export function memoListSubtitle(memo = null, preview = null) {
  const contact = memoContactName(memo, preview);
  const company = memoCompanyName(memo);
  if (contact && company && company.toLowerCase() !== contact.toLowerCase()) return company;
  return '';
}

export function memoHubspotContactId(memo = null) {
  return str(memo?.hubspotContactId || memo?.hubspot_contact_id) || null;
}

export function memoHubspotDealId(memo = null) {
  return str(
    memo?.hubspotDealId
    || memo?.hubspot_deal_id
    || memo?.matchedDealId
    || memo?.matched_deal_id,
  ) || null;
}

/**
 * Review writes the memo's contact even if the live tab is a different record.
 * A deal is optional — only used when the memo already has one.
 */
export function reviewIdsFromMemo(memo = null, pageTargets = {}) {
  const contactId = memoHubspotContactId(memo) || pageTargets.contactId || null;
  const memoDealId = memoHubspotDealId(memo);
  const dealId = memoDealId || null;
  return {
    contactId,
    dealId,
    skipDeal: !dealId,
  };
}
