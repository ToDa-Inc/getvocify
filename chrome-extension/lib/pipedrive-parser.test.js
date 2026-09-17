import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { parsePipedriveUrl, buildPipedriveUrl } from './pipedrive-parser.js';

describe('parsePipedriveUrl', () => {
  it('parses official deal and person URLs', () => {
    assert.deepEqual(parsePipedriveUrl('https://vocify2.pipedrive.com/deal/222'), {
      provider: 'pipedrive',
      companyDomain: 'vocify2',
      objectType: 'deal',
      recordId: '222',
    });
    assert.deepEqual(parsePipedriveUrl('https://vocify2.pipedrive.com/person/13?foo=1'), {
      provider: 'pipedrive',
      companyDomain: 'vocify2',
      objectType: 'contact',
      recordId: '13',
    });
  });

  it('parses organization pages', () => {
    assert.equal(
      parsePipedriveUrl('https://vocify2.pipedrive.com/organization/10')?.objectType,
      'company'
    );
  });

  it('ignores api host and non-record paths', () => {
    assert.equal(parsePipedriveUrl('https://api.pipedrive.com/deal/1'), null);
    assert.equal(parsePipedriveUrl('https://vocify2.pipedrive.com/deals/pipeline'), null);
  });
});

describe('buildPipedriveUrl', () => {
  it('round-trips deal and person', () => {
    const deal = parsePipedriveUrl('https://vocify2.pipedrive.com/deal/222/');
    assert.equal(buildPipedriveUrl(deal), 'https://vocify2.pipedrive.com/deal/222');
    assert.equal(
      buildPipedriveUrl({ companyDomain: 'vocify2', objectType: 'contact', recordId: '13' }),
      'https://vocify2.pipedrive.com/person/13'
    );
  });
});
