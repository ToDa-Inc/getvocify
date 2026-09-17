/**
 * Official Pipedrive record URLs:
 *   https://{company_domain}.pipedrive.com/deal/{id}
 *   https://{company_domain}.pipedrive.com/person/{id}
 * Organization uses the same host + /organization/{id} (Pipedrive web app).
 */

const PATH_TYPES = {
  deal: 'deal',
  person: 'contact',
  organization: 'company',
};

const BUILD_PATH = {
  deal: 'deal',
  contact: 'person',
  company: 'organization',
};

const SKIP_HOSTS = new Set(['api', 'oauth', 'www', 'developers', 'app']);

export function parsePipedriveUrl(url) {
  if (!url || typeof url !== 'string') return null;
  const match = url.match(
    /^https?:\/\/([a-z0-9-]+)\.pipedrive\.com\/(deal|person|organization)\/(\d+)/i
  );
  if (!match) return null;
  const companyDomain = match[1].toLowerCase();
  if (SKIP_HOSTS.has(companyDomain)) return null;
  const objectType = PATH_TYPES[match[2].toLowerCase()];
  return {
    provider: 'pipedrive',
    companyDomain,
    objectType,
    recordId: match[3],
  };
}

export function buildPipedriveUrl({ companyDomain, objectType, recordId }) {
  const path = BUILD_PATH[objectType];
  if (!companyDomain || !path || recordId == null || recordId === '') return '';
  return `https://${companyDomain}.pipedrive.com/${path}/${recordId}`;
}
