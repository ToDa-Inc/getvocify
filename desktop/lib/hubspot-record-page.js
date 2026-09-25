/**
 * Parse HubSpot CRM record URLs into { objectType, recordId } (same shape as extension context).
 */

const OBJECT_TYPES = {
  '0-1': 'contact',
  '0-2': 'company',
  '0-3': 'deal',
};

const LEGACY_PATH_TYPES = {
  contact: 'contact',
  company: 'company',
  deal: 'deal',
};

export function parseHubSpotRecordPage(url) {
  if (!url || typeof url !== 'string') return null;

  const recordMatch = url.match(
    /app(?:-(\w+))?\.hubspot\.com\/contacts\/(\d+)\/record\/([\d-]+)\/(\d+)/,
  );
  if (recordMatch) {
    const [, , , objectTypeId, recordId] = recordMatch;
    const objectType = OBJECT_TYPES[objectTypeId];
    if (!objectType || objectType === 'unknown') return null;
    return { objectType, recordId };
  }

  const legacyMatch = url.match(
    /app(?:-(\w+))?\.hubspot\.com\/contacts\/(\d+)\/(contact|company|deal)\/(\d+)/,
  );
  if (legacyMatch) {
    const [, , , pathType, recordId] = legacyMatch;
    const objectType = LEGACY_PATH_TYPES[pathType];
    if (!objectType) return null;
    return { objectType, recordId };
  }

  return null;
}
