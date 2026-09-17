import { parseHubSpotUrl } from './hubspot-parser.js';
import { parsePipedriveUrl } from './pipedrive-parser.js';

export function parseCrmPageUrl(url) {
  const pd = parsePipedriveUrl(url);
  if (pd) return pd;
  const hs = parseHubSpotUrl(url);
  return hs ? { ...hs, provider: 'hubspot' } : null;
}

export function crmDisplayName(providerOrUrl) {
  const s = String(providerOrUrl || '').toLowerCase();
  if (s === 'pipedrive' || s.includes('pipedrive.com')) return 'Pipedrive';
  if (s === 'salesforce' || s.includes('salesforce.com') || s.includes('.force.com')) {
    return 'Salesforce';
  }
  if (s === 'hubspot' || s.includes('hubspot.com')) return 'HubSpot';
  return 'your CRM';
}

export function crmContextPath(provider, objectType, recordId) {
  if (recordId == null || recordId === '') return null;
  const id = encodeURIComponent(String(recordId));
  if (provider === 'pipedrive') {
    const seg = { deal: 'deals', contact: 'persons', company: 'organizations' }[objectType];
    return seg ? `/crm/pipedrive/${seg}/${id}/context` : null;
  }
  const seg = { deal: 'deals', contact: 'contacts', company: 'companies' }[objectType];
  return seg ? `/crm/hubspot/${seg}/${id}/context` : null;
}

export function crmSearchPath(provider, kind, query) {
  const q = encodeURIComponent(query || '');
  if (provider === 'pipedrive') {
    const path = kind === 'contacts' ? 'persons' : 'deals';
    return `/crm/pipedrive/search/${path}?q=${q}`;
  }
  const path = kind === 'contacts' ? 'contacts' : 'deals';
  return `/crm/hubspot/search/${path}?q=${q}`;
}

export function crmConfigPath(provider) {
  return provider === 'pipedrive' ? '/crm/pipedrive/configuration' : '/crm/hubspot/configuration';
}

export function providerFromConnections(prefs, connections, fallback = 'hubspot') {
  const ok = (connections || []).filter((c) => c && c.status === 'connected');
  let target = ok.find((c) => c.id === prefs?.primary_crm_connection_id);
  if (!target && ok.length === 1) target = ok[0];
  return target?.provider || fallback;
}
